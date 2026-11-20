import base64
import hashlib
import io
import os
import re
import urllib.request
import zipfile
import matplotlib.font_manager as fm
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="在线检测 SPC 与过程能力分析系统 (v1.0 / v2.0)",
    page_icon="📈",
    layout="wide",
)

# ==================== 全局基础组件（图标、字体、文件读取） ====================
COPY_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"'
    ' viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>'
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2'
    ' 2v1"></path></svg>'
)

CHECK_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"'
    ' viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="20 6 9 17 4 12"></polyline></svg>'
)

BATCH_COLORS = ["#6495ED", "#E07A7A", "#34A853", "#9B6BDF", "#F29900"]
BATCH_EDGE_COLORS = ["#3B5998", "#A8383B", "#1E7E34", "#5E35B1", "#B06000"]


def render_copy_image_button(png_bytes, btn_key):
  b64_png = base64.b64encode(png_bytes).decode("ascii")
  safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", btn_key)
  html_code = f"""
    <div style="display:flex;align-items:center;gap:6px;height:38px;margin:0;padding:0;">
      <button id="btn_{safe_id}" type="button" title="复制图片"
        style="display:inline-flex;align-items:center;justify-content:center;
               width:38px;height:38px;border-radius:8px;
               border:1px solid rgba(150,150,160,0.38);
               background:transparent;color:inherit;cursor:pointer;
               transition:background 0.15s ease,border-color 0.15s ease;">
        {COPY_ICON_SVG}
      </button>
      <span id="msg_{safe_id}" style="font-size:12px;white-space:nowrap;opacity:0.85;"></span>
    </div>
    <script>
      (function() {{
        const btn = document.getElementById("btn_{safe_id}");
        const msg = document.getElementById("msg_{safe_id}");
        const copySvg = `{COPY_ICON_SVG}`;
        const checkSvg = `{CHECK_ICON_SVG}`;
        const b64Data = "{b64_png}";
        if (!btn) return;
        btn.addEventListener("mouseenter", () => {{
          btn.style.background = "rgba(128,128,128,0.15)";
          btn.style.borderColor = "rgba(150,150,160,0.6)";
        }});
        btn.addEventListener("mouseleave", () => {{
          btn.style.background = "transparent";
          btn.style.borderColor = "rgba(150,150,160,0.38)";
        }});
        btn.addEventListener("click", async () => {{
          try {{
            const binStr = atob(b64Data);
            const len = binStr.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {{
              bytes[i] = binStr.charCodeAt(i);
            }}
            const blob = new Blob([bytes], {{ type: "image/png" }});
            if (navigator.clipboard && window.ClipboardItem) {{
              await navigator.clipboard.write([new ClipboardItem({{ "image/png": blob }})]);
              btn.innerHTML = checkSvg;
              msg.textContent = "已复制";
              setTimeout(() => {{
                btn.innerHTML = copySvg;
                msg.textContent = "";
              }}, 1800);
            }} else {{
              msg.textContent = "不支持复制，请点下载";
            }}
          }} catch (err) {{
            msg.textContent = "复制受限，请点下载";
          }}
        }});
      }})();
    </script>
    """
  components.html(html_code, height=40)


def render_chart_action_bar(png_bytes, file_name, key_prefix):
  a1, a2, _ = st.columns([0.85, 2.15, 7.0], gap="small")
  with a1:
    st.download_button(
        "下载",
        data=png_bytes,
        file_name=file_name,
        mime="image/png",
        key=f"dl_{key_prefix}",
        use_container_width=True,
    )
  with a2:
    render_copy_image_button(png_bytes, f"cp_{key_prefix}")


@st.cache_resource
def init_chinese_font():
  system_paths = [
      "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
      "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
      "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
      "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
      "C:/Windows/Fonts/msyh.ttc",
      "C:/Windows/Fonts/simhei.ttf",
      "/System/Library/Fonts/PingFang.ttc",
  ]
  for path in system_paths:
    if os.path.exists(path):
      return path

  font_dir = os.path.join(os.path.expanduser("~"), ".cache", "spc_fonts")
  os.makedirs(font_dir, exist_ok=True)
  local_font_path = os.path.join(font_dir, "NotoSansSC-Regular.ttf")

  if (
      not os.path.exists(local_font_path)
      or os.path.getsize(local_font_path) < 100000
  ):
    font_urls = [
        "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
        "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
        "https://raw.githubusercontent.com/StellarCN/scp_zh/master/fonts/SimHei.ttf",
    ]
    for url in font_urls:
      try:
        urllib.request.urlretrieve(url, local_font_path)
        if (
            os.path.exists(local_font_path)
            and os.path.getsize(local_font_path) > 100000
        ):
          break
      except Exception:
        continue

  if (
      os.path.exists(local_font_path)
      and os.path.getsize(local_font_path) > 100000
  ):
    return local_font_path
  return None


FONT_PATH = init_chinese_font()
if FONT_PATH:
  fm.fontManager.addfont(FONT_PATH)
  FONT_PROP = fm.FontProperties(fname=FONT_PATH)
  plt.rcParams["font.family"] = "sans-serif"
  plt.rcParams["font.sans-serif"] = [FONT_PROP.get_name(), "DejaVu Sans"]
else:
  FONT_PROP = fm.FontProperties()
  plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]

plt.rcParams["axes.unicode_minus"] = False


def read_csv_compatible(file_bytes):
  encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk", "big5"]
  last_err = None
  for enc in encodings:
    try:
      df = pd.read_csv(
          io.BytesIO(file_bytes),
          encoding=enc,
          sep=None,
          engine="python",
      )
      if df is not None and not df.empty:
        return df
    except UnicodeDecodeError as e:
      last_err = e
      continue
    except Exception:
      try:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
        if df is not None and not df.empty:
          return df
      except Exception as e2:
        last_err = e2
        continue

  try:
    text_fallback = file_bytes.decode("gb18030", errors="replace")
    return pd.read_csv(io.StringIO(text_fallback), sep=None, engine="python")
  except Exception:
    raise last_err if last_err else ValueError("无法解析 CSV 文件")


@st.cache_data(show_spinner=False, max_entries=8)
def load_workbook_sheets(file_bytes, filename):
  lower_name = filename.lower()
  if lower_name.endswith(".csv"):
    df = read_csv_compatible(file_bytes)
    sheet_label = os.path.splitext(filename)[0] or "CSV_Data"
    return {sheet_label: df}

  engine = "openpyxl" if lower_name.endswith(".xlsx") else None
  xls = pd.ExcelFile(io.BytesIO(file_bytes), engine=engine)
  result = {}
  for name in xls.sheet_names:
    try:
      part_df = xls.parse(name)
      if part_df is not None and not part_df.dropna(how="all").empty:
        result[name] = part_df
    except Exception:
      continue
  if not result:
    result[xls.sheet_names[0]] = pd.DataFrame()
  return result


def detect_spec_from_columns(df, all_cols):
  lsl_col, target_col, usl_col = None, None, None
  lsl_keywords = ["规格下限", "下限", "下公差", "lsl", "lower"]
  target_keywords = [
      "目标值",
      "目标",
      "中心值",
      "标准值",
      "target",
      "nominal",
      "center",
  ]
  usl_keywords = ["规格上限", "上限", "上公差", "usl", "upper"]

  for col in all_cols:
    if col in ("Row_Index", "Source_Batch"):
      continue
    col_clean = str(col).strip().lower()
    if lsl_col is None and any(k in col_clean for k in lsl_keywords):
      lsl_col = col
    elif usl_col is None and any(k in col_clean for k in usl_keywords):
      usl_col = col
    elif target_col is None and any(k in col_clean for k in target_keywords):
      target_col = col

  def extract_representative_val(col_name):
    if col_name is None:
      return None
    s = pd.to_numeric(df[col_name], errors="coerce").dropna()
    if s.empty:
      return None
    modes = s.mode()
    return float(modes.iloc[0]) if not modes.empty else float(s.iloc[0])

  detected_lsl = extract_representative_val(lsl_col)
  detected_target = extract_representative_val(target_col)
  detected_usl = extract_representative_val(usl_col)
  spec_cols_found = {c for c in [lsl_col, target_col, usl_col] if c is not None}
  return {
      "lsl": detected_lsl,
      "target": detected_target,
      "usl": detected_usl,
      "spec_cols": spec_cols_found,
  }


def is_likely_non_measurement(name_str):
  s = str(name_str).strip().lower()
  non_meas_tokens = [
      "日期",
      "时间",
      "date",
      "time",
      "timestamp",
      "ea号",
      "编号",
      "序号",
      "工单",
      "卷号",
      "批次",
      "id",
      "no",
      "code",
      "速度",
      "speed",
      "走带",
      "长度",
      "米数",
      "meter",
      "len",
      "ok(",
      "ng(",
  ]
  return any(tok in s for tok in non_meas_tokens)


def infer_parameter_groups(cols):
  groups = {}
  order = []
  for c in cols:
    s = str(c).strip()
    prefix = re.sub(r"[\s_\-#]*\d+$", "", s).strip()
    if not prefix:
      prefix = s
    if prefix not in groups:
      groups[prefix] = []
      order.append(prefix)
    groups[prefix].append(c)
  return order, groups


@st.cache_data(show_spinner=False, max_entries=32)
def parse_exclude_indices(range_text, max_row):
  excluded = set()
  if not range_text.strip():
    return excluded
  parts = re.split(r"[,，;；\s]+", range_text.strip())
  for part in parts:
    if not part:
      continue
    if "-" in part:
      bounds = part.split("-", 1)
      try:
        start_r = max(1, int(bounds[0]))
        end_r = min(max_row, int(bounds[1]))
        if start_r <= end_r:
          excluded.update(range(start_r, end_r + 1))
      except ValueError:
        pass
    else:
      try:
        r = int(part)
        if 1 <= r <= max_row:
          excluded.add(r)
      except ValueError:
        pass
  return excluded


def compute_within_std(mat, flat_vals):
  s_ov = float(np.std(flat_vals, ddof=1))
  if mat.shape[1] >= 2:
    r_counts = np.sum(~np.isnan(mat), axis=1)
    v_rows = r_counts >= 2
    if np.any(v_rows):
      s_val = mat[v_rows]
      r_means = np.nanmean(s_val, axis=1, keepdims=True)
      ss_w = np.nansum((s_val - r_means) ** 2)
      df_w = np.sum(r_counts[v_rows] - 1)
      return float(np.sqrt(ss_w / df_w)) if df_w > 0 else s_ov
    return s_ov
  mr_arr = np.abs(np.diff(flat_vals))
  m_mr = float(np.mean(mr_arr)) if len(mr_arr) > 0 else 0.0
  return m_mr / 1.12838 if m_mr > 0 else s_ov


def _downsample_xy(x_arr, y_arr, max_pts=4000):
  n = len(x_arr)
  if n <= max_pts:
    return x_arr, y_arr
  step = max(1, n // max_pts)
  return x_arr[::step], y_arr[::step]


def _compute_spc_metrics_from_clean(
    df_c,
    df_r,
    cell_cnt,
    valid_cols,
    p_lsl,
    p_target,
    p_usl,
    apply_tuning,
    center_align_pct,
    tuning_mode,
    manual_target_sigma,
    target_cpk_goal,
    extra_meta=None,
):
  s_mat_raw = df_c[valid_cols].to_numpy(dtype=np.float32)
  v_vals_raw = s_mat_raw[~np.isnan(s_mat_raw)]
  if len(v_vals_raw) < 2:
    return None

  orig_m = float(np.mean(v_vals_raw))
  orig_wi = compute_within_std(s_mat_raw, v_vals_raw)

  if apply_tuning and orig_wi > 0:
    adj_mean = orig_m + (p_target - orig_m) * (center_align_pct / 100.0)
    if tuning_mode == "直接指定目标西格玛 (σ)" and manual_target_sigma is not None:
      tgt_wi = float(manual_target_sigma)
    else:
      min_dist = min(p_usl - adj_mean, adj_mean - p_lsl)
      tgt_wi = min_dist / (3.0 * target_cpk_goal) if min_dist > 0 else orig_wi
    ratio = tgt_wi / orig_wi
    for c_name in valid_cols:
      df_c[c_name] = adj_mean + (df_c[c_name] - orig_m) * ratio
    df_c["_Row_Mean_"] = df_c[valid_cols].mean(axis=1)

  s_mat = df_c[valid_cols].to_numpy(dtype=np.float32)
  v_vals = s_mat[~np.isnan(s_mat)]
  s_mean = float(np.mean(v_vals))
  s_ov = float(np.std(v_vals, ddof=1))
  s_wi = compute_within_std(s_mat, v_vals)
  tot_n = int(len(v_vals))

  cp_v = (p_usl - p_lsl) / (6.0 * s_wi) if s_wi > 0 else np.nan
  cpl_v = (s_mean - p_lsl) / (3.0 * s_wi) if s_wi > 0 else np.nan
  cpu_v = (p_usl - s_mean) / (3.0 * s_wi) if s_wi > 0 else np.nan
  cpk_v = min(cpl_v, cpu_v)

  pp_v = (p_usl - p_lsl) / (6.0 * s_ov) if s_ov > 0 else np.nan
  ppl_v = (s_mean - p_lsl) / (3.0 * s_ov) if s_ov > 0 else np.nan
  ppu_v = (p_usl - s_mean) / (3.0 * s_ov) if s_ov > 0 else np.nan
  ppk_v = min(ppl_v, ppu_v)

  obs_lt = float(np.sum(v_vals < p_lsl)) / tot_n * 1e6
  obs_gt = float(np.sum(v_vals > p_usl)) / tot_n * 1e6
  obs_tot = obs_lt + obs_gt

  exp_ov_lt = (
      stats.norm.cdf((p_lsl - s_mean) / s_ov) * 1e6 if s_ov > 0 else 0.0
  )
  exp_ov_gt = (
      (1.0 - stats.norm.cdf((p_usl - s_mean) / s_ov)) * 1e6 if s_ov > 0 else 0.0
  )
  exp_ov_tot = exp_ov_lt + exp_ov_gt

  exp_wi_lt = (
      stats.norm.cdf((p_lsl - s_mean) / s_wi) * 1e6 if s_wi > 0 else 0.0
  )
  exp_wi_gt = (
      (1.0 - stats.norm.cdf((p_usl - s_mean) / s_wi)) * 1e6 if s_wi > 0 else 0.0
  )
  exp_wi_tot = exp_wi_lt + exp_wi_gt

  out = {
      "cols": valid_cols,
      "lsl": p_lsl,
      "target": p_target,
      "usl": p_usl,
      "df_clean": df_c,
      "df_removed": df_r,
      "masked_cells": cell_cnt,
      "all_valid_vals": v_vals,
      "val_min": float(np.min(v_vals)),
      "val_max": float(np.max(v_vals)),
      "total_n": tot_n,
      "sample_mean": s_mean,
      "std_overall": s_ov,
      "std_within": s_wi,
      "cp": cp_v,
      "cpl": cpl_v,
      "cpu": cpu_v,
      "cpk": cpk_v,
      "pp": pp_v,
      "ppl": ppl_v,
      "ppu": ppu_v,
      "ppk": ppk_v,
      "obs_lt_lsl": obs_lt,
      "obs_gt_usl": obs_gt,
      "obs_total": obs_tot,
      "exp_ov_lt_lsl": exp_ov_lt,
      "exp_ov_gt_usl": exp_ov_gt,
      "exp_ov_total": exp_ov_tot,
      "exp_wi_lt_lsl": exp_wi_lt,
      "exp_wi_gt_usl": exp_wi_gt,
      "exp_wi_total": exp_wi_tot,
  }
  if extra_meta:
    out.update(extra_meta)
  return out


@st.cache_data(show_spinner=False, max_entries=16)
def cached_build_v1_bundle(
    df_raw,
    proj_cols,
    p_lsl,
    p_target,
    p_usl,
    spike_mode,
    spike_param_val,
    spike_action,
    pt_min_val,
    pt_max_val,
    exclude_ranges_str,
    filter_mode,
    custom_min,
    custom_max,
    apply_tuning,
    center_align_pct,
    tuning_mode,
    manual_target_sigma,
    target_cpk_goal,
):
  valid_cols = [c for c in proj_cols if c in df_raw.columns]
  if not valid_cols:
    return None

  excl_set = parse_exclude_indices(exclude_ranges_str, len(df_raw))
  df_w = df_raw.copy()
  sub_raw = df_w[valid_cols].to_numpy(dtype=np.float32)
  sp_mask = np.zeros_like(sub_raw, dtype=bool)

  if spike_mode != "不启用单点屏蔽":
    if spike_mode == "智能抗差识别（偏离中位数 N 倍 MAD）":
      v_flat = sub_raw[~np.isnan(sub_raw)]
      if len(v_flat) > 0:
        med_v = float(np.median(v_flat))
        mad_v = float(np.median(np.abs(v_flat - med_v)))
        r_sig = mad_v * 1.4826
        if r_sig <= 1e-12:
          q75, q25 = np.percentile(v_flat, [75, 25])
          r_sig = max((q75 - q25) / 1.349, (p_usl - p_lsl) / 6.0, 1e-6)
        low_b = med_v - spike_param_val * r_sig
        high_b = med_v + spike_param_val * r_sig
        sp_mask = (~np.isnan(sub_raw)) & (
            (sub_raw < low_b) | (sub_raw > high_b)
        )
    elif spike_mode == "按各项目 SPEC 公差倍数识别":
      sp_span = p_usl - p_lsl
      low_b = p_target - spike_param_val * sp_span
      high_b = p_target + spike_param_val * sp_span
      sp_mask = (~np.isnan(sub_raw)) & (
          (sub_raw < low_b) | (sub_raw > high_b)
      )
    elif (
        spike_mode == "自定义单点有效数值区间"
        and pt_min_val is not None
        and pt_max_val is not None
    ):
      sp_mask = (~np.isnan(sub_raw)) & (
          (sub_raw < pt_min_val) | (sub_raw > pt_max_val)
      )

  cell_cnt = int(np.sum(sp_mask))
  row_has_sp = np.any(sp_mask, axis=1)

  if cell_cnt > 0 and spike_action == "置空该单元格（保留行内其他列）":
    cleaned = sub_raw.copy()
    cleaned[sp_mask] = np.nan
    for idx_c, c_name in enumerate(valid_cols):
      df_w[c_name] = cleaned[:, idx_c]

  df_w["_Row_Mean_"] = df_w[valid_cols].mean(axis=1)

  m_not_nan = df_w["_Row_Mean_"].notna()
  m_not_rng = ~df_w["Row_Index"].isin(excl_set)
  m_no_sp_row = (
      pd.Series(~row_has_sp, index=df_w.index)
      if (cell_cnt > 0 and spike_action == "剔除包含异常点的整行")
      else pd.Series(True, index=df_w.index)
  )
  m_val_ok = pd.Series(True, index=df_w.index)

  if filter_mode == "按各项目 SPEC 范围过滤":
    m_val_ok = (df_w["_Row_Mean_"] >= p_lsl) & (df_w["_Row_Mean_"] <= p_usl)
  elif (
      filter_mode == "按自定义范围过滤（超出设定区间屏蔽）"
      and custom_min is not None
      and custom_max is not None
  ):
    m_val_ok = (df_w["_Row_Mean_"] >= custom_min) & (
        df_w["_Row_Mean_"] <= custom_max
    )

  v_mask = m_not_nan & m_not_rng & m_no_sp_row & m_val_ok
  df_c = df_w[v_mask].copy().reset_index(drop=True)
  df_r = df_raw[~v_mask].copy().reset_index(drop=True)

  return _compute_spc_metrics_from_clean(
      df_c,
      df_r,
      cell_cnt,
      valid_cols,
      p_lsl,
      p_target,
      p_usl,
      apply_tuning,
      center_align_pct,
      tuning_mode,
      manual_target_sigma,
      target_cpk_goal,
  )


@st.cache_data(show_spinner=False, max_entries=24)
def cached_prefilter_v2_batch(
    df_src,
    batch_label,
    proj_cols,
    p_lsl,
    p_target,
    p_usl,
    spike_mode,
    spike_param_val,
    spike_action,
    pt_min_val,
    pt_max_val,
    exclude_ranges_str,
    filter_mode,
    custom_min,
    custom_max,
):
  valid_cols = [c for c in proj_cols if c in df_src.columns]
  if not valid_cols:
    return None

  excl_set = parse_exclude_indices(exclude_ranges_str, len(df_src))
  df_w = df_src.copy()
  sub_raw = df_w[valid_cols].to_numpy(dtype=np.float32)
  sp_mask = np.zeros_like(sub_raw, dtype=bool)

  if spike_mode != "不启用单点屏蔽":
    if spike_mode == "智能抗差识别（偏离中位数 N 倍 MAD）":
      v_flat = sub_raw[~np.isnan(sub_raw)]
      if len(v_flat) > 0:
        med_v = float(np.median(v_flat))
        mad_v = float(np.median(np.abs(v_flat - med_v)))
        r_sig = mad_v * 1.4826
        if r_sig <= 1e-12:
          q75, q25 = np.percentile(v_flat, [75, 25])
          r_sig = max((q75 - q25) / 1.349, (p_usl - p_lsl) / 6.0, 1e-6)
        low_b = med_v - spike_param_val * r_sig
        high_b = med_v + spike_param_val * r_sig
        sp_mask = (~np.isnan(sub_raw)) & (
            (sub_raw < low_b) | (sub_raw > high_b)
        )
    elif spike_mode == "按各项目 SPEC 公差倍数识别":
      sp_span = p_usl - p_lsl
      low_b = p_target - spike_param_val * sp_span
      high_b = p_target + spike_param_val * sp_span
      sp_mask = (~np.isnan(sub_raw)) & (
          (sub_raw < low_b) | (sub_raw > high_b)
      )
    elif (
        spike_mode == "自定义单点有效数值区间"
        and pt_min_val is not None
        and pt_max_val is not None
    ):
      sp_mask = (~np.isnan(sub_raw)) & (
          (sub_raw < pt_min_val) | (sub_raw > pt_max_val)
      )

  cell_cnt = int(np.sum(sp_mask))
  row_has_sp = np.any(sp_mask, axis=1)

  if cell_cnt > 0 and spike_action == "置空该单元格（保留行内其他列）":
    cleaned = sub_raw.copy()
    cleaned[sp_mask] = np.nan
    for idx_c, c_name in enumerate(valid_cols):
      df_w[c_name] = cleaned[:, idx_c]

  df_w["_Row_Mean_"] = df_w[valid_cols].mean(axis=1)

  m_not_nan = df_w["_Row_Mean_"].notna()
  m_not_rng = ~df_w["Row_Index"].isin(excl_set)
  m_no_sp_row = (
      pd.Series(~row_has_sp, index=df_w.index)
      if (cell_cnt > 0 and spike_action == "剔除包含异常点的整行")
      else pd.Series(True, index=df_w.index)
  )
  m_val_ok = pd.Series(True, index=df_w.index)

  if filter_mode == "按各项目 SPEC 范围过滤":
    m_val_ok = (df_w["_Row_Mean_"] >= p_lsl) & (df_w["_Row_Mean_"] <= p_usl)
  elif (
      filter_mode == "按自定义范围过滤（超出设定区间屏蔽）"
      and custom_min is not None
      and custom_max is not None
  ):
    m_val_ok = (df_w["_Row_Mean_"] >= custom_min) & (
        df_w["_Row_Mean_"] <= custom_max
    )

  v_mask = m_not_nan & m_not_rng & m_no_sp_row & m_val_ok
  df_c = df_w[v_mask].copy().reset_index(drop=True)
  df_r = df_src[~v_mask].copy().reset_index(drop=True)
  if len(df_c) < 2:
    return None

  return {
      "batch_label": batch_label,
      "valid_cols": valid_cols,
      "df_clean": df_c,
      "df_removed": df_r,
      "masked_cells": cell_cnt,
  }


def save_fig_with_border(fig, show_outer_border=True, use_tight=False):
  fig.patch.set_facecolor("white")
  buf = io.BytesIO()
  try:
    if use_tight:
      if show_outer_border:
        fig.canvas.draw()
        renderer = getattr(fig.canvas, "get_renderer", lambda: None)()
        fig_w_in, fig_h_in = fig.get_size_inches()
        pad_in = 0.14
        if renderer is not None:
          bbox_in = fig.get_tightbbox(renderer)
          if (
              bbox_in is not None
              and bbox_in.width > 0
              and bbox_in.height > 0
              and fig_w_in > 0
              and fig_h_in > 0
          ):
            x0 = (bbox_in.x0 - pad_in) / fig_w_in
            y0 = (bbox_in.y0 - pad_in) / fig_h_in
            w_norm = (bbox_in.width + 2 * pad_in) / fig_w_in
            h_norm = (bbox_in.height + 2 * pad_in) / fig_h_in
            border_rect = Rectangle(
                (x0, y0),
                w_norm,
                h_norm,
                transform=fig.transFigure,
                fill=False,
                edgecolor="#A6A6A6",
                linewidth=1.2,
                zorder=100,
                clip_on=False,
            )
            fig.patches.append(border_rect)
        fig.savefig(
            buf, format="png", dpi=150, bbox_inches="tight", pad_inches=pad_in
        )
      else:
        fig.savefig(
            buf, format="png", dpi=150, bbox_inches="tight", pad_inches=0.14
        )
    else:
      if show_outer_border:
        fig.patch.set_edgecolor("#A6A6A6")
        fig.patch.set_linewidth(2.2)
      fig.savefig(
          buf,
          format="png",
          dpi=150,
          facecolor=fig.get_facecolor(),
          edgecolor=fig.get_edgecolor(),
      )
  except Exception:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140)
  plt.close(fig)
  return buf.getvalue()


def _bundle_fingerprint(b):
  h = hashlib.md5()
  h.update(
      f"{b['total_n']}|{b['sample_mean']:.6f}|{b['std_overall']:.6f}|{b['std_within']:.6f}|"
      f"{b['lsl']:.6f}|{b['target']:.6f}|{b['usl']:.6f}|{','.join(map(str, b['cols']))}".encode(
          "utf-8"
      )
  )
  arr = b["all_valid_vals"]
  if len(arr) > 0:
    h.update(
        f"{float(arr[0]):.6f}|{float(arr[-1]):.6f}|{float(np.sum(arr[: min(200, len(arr))])):.6f}".encode(
            "utf-8"
        )
    )
  return h.hexdigest()


# ==================== 首页版本模式入口 ====================
if "app_mode" not in st.session_state:
  st.session_state["app_mode"] = "home"


def render_landing_page():
  st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
  st.title("在线检测 SPC 与过程能力分析系统")
  st.caption("Created by xu  |  请选择分析模式进入对应工作台")
  st.markdown("---")

  col_v1, col_v2 = st.columns(2, gap="large")

  with col_v1:
    st.markdown(
        """
            <div style="border:1px solid rgba(148,163,184,0.35);border-radius:12px;
                        padding:22px 24px;background:rgba(148,163,184,0.05);min-height:230px;">
              <div style="display:inline-block;background:#475569;color:#FFFFFF;
                          font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;">
                v1.0 · 单批 / 多批叠加分析版
              </div>
              <h3 style="margin:12px 0 8px 0;">📈 全套 SPC 深度分析（支持多文件堆叠）</h3>
              <p style="font-size:14px;line-height:1.65;opacity:0.9;">
                适用于单批次深度评估，也支持<strong>多同表头批次文件往下堆叠合并</strong>以扩充样本量：
              </p>
              <ul style="font-size:13.5px;line-height:1.75;padding-left:18px;margin-bottom:0;">
                <li>支持单文件或<strong>多同表头文件纵向堆叠</strong>，自定义比例（4:3 / 16:9 / 2.2:1 等）</li>
                <li>过程能力报告（CPK/PPK）、分组箱线图、时间序列图、散点序列图、单行均值趋势图</li>
                <li>支持单点极端尖峰屏蔽与西格玛 / CPK 波动校准</li>
              </ul>
            </div>
            """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    if st.button(
        "进入 1.0 分析工作台",
        key="enter_v1_btn",
        use_container_width=True,
    ):
      st.session_state["app_mode"] = "v1"
      st.rerun()

  with col_v2:
    st.markdown(
        """
            <div style="border:1.5px solid #2563EB;border-radius:12px;
                        padding:22px 24px;background:rgba(37,99,235,0.06);min-height:230px;">
              <div style="display:inline-block;background:#2563EB;color:#FFFFFF;
                          font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;">
                v2.0 · 多批次对比版（NEW）
              </div>
              <h3 style="margin:12px 0 8px 0;">📊 多批次同屏对比与汇报筛选</h3>
              <p style="font-size:14px;line-height:1.65;opacity:0.9;">
                适用于同时对比 <strong>2–3 个同表头批次文件</strong>，快速筛选最适合展示汇报的批次：
              </p>
              <ul style="font-size:13.5px;line-height:1.75;padding-left:18px;margin-bottom:0;">
                <li>新增<strong>多批次含组直方图（可叠加正态拟合线）</strong>，直观对比各批次分布</li>
                <li>支持<strong>自定义样本区间</strong>（对齐最短样本或指定起止序号），避免长短不一</li>
                <li>保留单点极端尖峰屏蔽与西格玛 / CPK 波动校准</li>
              </ul>
            </div>
            """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    if st.button(
        "进入 2.0 多批次对比",
        key="enter_v2_btn",
        type="primary",
        use_container_width=True,
    ):
      st.session_state["app_mode"] = "v2"
      st.rerun()


def render_sidebar_mode_switcher(current_mode):
  with st.sidebar:
    badge_bg = "#475569" if current_mode == "v1" else "#2563EB"
    badge_txt = (
        "当前模式：v1.0 单批 / 多批叠加版"
        if current_mode == "v1"
        else "当前模式：v2.0 多批次对比版"
    )
    st.markdown(
        f"<div style='background:{badge_bg};color:#fff;font-size:12px;font-weight:700;"
        f"padding:5px 10px;border-radius:6px;text-align:center;margin-bottom:8px;'>"
        f"{badge_txt}</div>",
        unsafe_allow_html=True,
    )
    nav1, nav2 = st.columns(2)
    if nav1.button(
        "🏠 首页", key=f"go_home_{current_mode}", use_container_width=True
    ):
      st.session_state["app_mode"] = "home"
      st.rerun()
    target_m = "v2" if current_mode == "v1" else "v1"
    target_lbl = "切至 2.0" if current_mode == "v1" else "切至 1.0"
    if nav2.button(
        target_lbl, key=f"switch_to_{target_m}", use_container_width=True
    ):
      st.session_state["app_mode"] = target_m
      st.rerun()
    st.markdown("---")


# ==================== 轻量参数缓存绘图函数（避免把大 DataFrame 塞进缓存 key） ====================
@st.cache_data(show_spinner=False, max_entries=16)
def cached_capability_png(
    data_fp,
    all_v,
    tot_n,
    valid_rows_cnt,
    sub_cnt,
    s_mean,
    s_ov,
    s_wi,
    pp,
    ppl,
    ppu,
    ppk,
    cp,
    cpl,
    cpu,
    cpk,
    obs_lt,
    obs_gt,
    obs_tot,
    exp_ov_lt,
    exp_ov_gt,
    exp_ov_tot,
    exp_wi_lt,
    exp_wi_gt,
    exp_wi_tot,
    p_lsl,
    p_target,
    p_usl,
    title_str,
    w_in,
    h_in,
    show_outer_border,
):
  fig = plt.figure(figsize=(w_in, h_in), dpi=150)
  scale_f = min(w_in / 9.6, h_in / 7.2)
  font_panel = max(7.2, 8.3 * scale_f)
  font_title = max(11.5, 13.5 * scale_f)

  gs = fig.add_gridspec(
      2,
      3,
      width_ratios=[1.05, 2.35, 0.95],
      height_ratios=[3.6, 1.15],
      wspace=0.06,
      hspace=0.22,
  )
  ax_left = fig.add_subplot(gs[0, 0])
  ax_mid = fig.add_subplot(gs[0, 1])
  ax_right = fig.add_subplot(gs[0, 2])
  ax_bot_left = fig.add_subplot(gs[1, 0])
  ax_bot_mid = fig.add_subplot(gs[1, 1])
  ax_bot_right = fig.add_subplot(gs[1, 2])
  for ax_tmp in (ax_left, ax_right, ax_bot_left, ax_bot_mid, ax_bot_right):
    ax_tmp.axis("off")

  bins_count = min(38, max(14, int(np.sqrt(tot_n) * 0.55)))
  counts, _, _ = ax_mid.hist(
      all_v,
      bins=bins_count,
      density=True,
      color="#78A2CC",
      edgecolor="#3A5F85",
      linewidth=0.55,
      alpha=0.92,
  )

  span = max(p_usl - p_lsl, 1e-6)
  x_min_c = min(p_lsl - 0.18 * span, float(np.min(all_v)) - 0.08 * span)
  x_max_c = max(p_usl + 0.18 * span, float(np.max(all_v)) + 0.08 * span)
  x_grid = np.linspace(x_min_c, x_max_c, 400)

  line_ov, line_wi = None, None
  if s_ov > 1e-12:
    (line_ov,) = ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, s_mean, s_ov),
        color="#B91C1C",
        lw=1.8,
        label="Overall",
    )
  if s_wi > 1e-12:
    (line_wi,) = ax_mid.plot(
        x_grid,
        stats.norm.pdf(x_grid, s_mean, s_wi),
        color="#374151",
        lw=1.6,
        ls="--",
        label="Within",
    )

  ax_mid.axvline(p_lsl, color="#DC2626", ls="--", lw=1.15)
  ax_mid.axvline(p_usl, color="#DC2626", ls="--", lw=1.15)
  ax_mid.axvline(p_target, color="#16A34A", ls=":", lw=1.1)

  y_peak = max(
      float(np.max(counts)) if len(counts) else 1.0,
      float(np.max(stats.norm.pdf(x_grid, s_mean, s_wi)))
      if s_wi > 1e-12
      else 1.0,
      1e-6,
  )
  ax_mid.set_ylim(0, y_peak * 1.14)
  ax_mid.set_yticks([])
  ax_mid.tick_params(axis="x", labelsize=max(7.5, 8.8 * scale_f))
  ax_mid.grid(True, axis="x", ls=":", alpha=0.45)

  lbl_sz = max(7.5, 8.5 * scale_f)
  ax_mid.text(
      p_lsl,
      y_peak * 1.16,
      f"LSL\n{p_lsl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
      fontweight="bold",
  )
  ax_mid.text(
      p_usl,
      y_peak * 1.16,
      f"USL\n{p_usl:.2f}",
      color="#B91C1C",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
      fontweight="bold",
  )
  ax_mid.text(
      p_target,
      y_peak * 1.16,
      f"Target\n{p_target:.2f}",
      color="#15803D",
      ha="center",
      va="bottom",
      fontsize=lbl_sz,
  )

  left_text = (
      f"Process Data\n----------------------\n"
      f"LSL          {p_lsl:.4f}\nTarget       {p_target:.4f}\nUSL          {p_usl:.4f}\n"
      f"Mean         {s_mean:.4f}\nSample N     {tot_n}\nValid Rows   {valid_rows_cnt}\n"
      f"Subgroup     {sub_cnt}\nStDev(Ov)    {s_ov:.5f}\nStDev(Wi)    {s_wi:.5f}"
  )
  ax_left.text(
      0.95,
      0.96,
      left_text,
      transform=ax_left.transAxes,
      va="top",
      ha="right",
      fontsize=font_panel,
      fontfamily="monospace",
      color="#1E293B",
  )

  right_text = (
      f"Overall Capability\n------------------\n"
      f"Pp        {pp:.2f}\nPPL       {ppl:.2f}\nPPU       {ppu:.2f}\nPpk       {ppk:.2f}\n\n"
      f"Potential (Within)\n------------------\n"
      f"Cp        {cp:.2f}\nCPL       {cpl:.2f}\nCPU       {cpu:.2f}\nCpk       {cpk:.2f}"
  )
  ax_right.text(
      0.06,
      0.96,
      right_text,
      transform=ax_right.transAxes,
      va="top",
      ha="left",
      fontsize=font_panel,
      fontfamily="monospace",
      color="#1E293B",
  )

  handles_leg = [h for h in (line_ov, line_wi) if h is not None]
  if handles_leg:
    ax_bot_right.legend(
        handles=handles_leg,
        loc="upper left",
        bbox_to_anchor=(0.04, 0.98),
        fontsize=font_panel,
    )

  ppm_text = (
      f"Performance (PPM)        Observed    Exp. Overall    Exp. Within\n"
      f"----------------------------------------------------------------\n"
      f"PPM < LSL               {obs_lt:9.2f}       {exp_ov_lt:9.2f}      {exp_wi_lt:9.2f}\n"
      f"PPM > USL               {obs_gt:9.2f}       {exp_ov_gt:9.2f}      {exp_wi_gt:9.2f}\n"
      f"Total PPM               {obs_tot:9.2f}       {exp_ov_tot:9.2f}      {exp_wi_tot:9.2f}"
  )
  ax_bot_mid.text(
      0.5,
      0.92,
      ppm_text,
      transform=ax_bot_mid.transAxes,
      va="top",
      ha="center",
      fontsize=max(7.0, font_panel * 0.96),
      fontfamily="monospace",
      color="#1E293B",
      bbox=dict(
          boxstyle="round,pad=0.4", facecolor="#F8FAFC", edgecolor="#E2E8F0"
      ),
  )

  fig.suptitle(
      title_str,
      fontsize=font_title,
      fontweight="bold",
      y=0.96,
      fontproperties=FONT_PROP,
  )
  plt.subplots_adjust(left=0.025, right=0.975, top=0.835, bottom=0.045)
  return save_fig_with_border(fig, show_outer_border, use_tight=False)


def render_capability_from_bundle(
    b, title_str, w_in, h_in, show_outer_border
):
  return cached_capability_png(
      b["fp"],
      b["all_valid_vals"],
      b["total_n"],
      len(b["df_clean"]),
      len(b["cols"]),
      b["sample_mean"],
      b["std_overall"],
      b["std_within"],
      b["pp"],
      b["ppl"],
      b["ppu"],
      b["ppk"],
      b["cp"],
      b["cpl"],
      b["cpu"],
      b["cpk"],
      b["obs_lt_lsl"],
      b["obs_gt_usl"],
      b["obs_total"],
      b["exp_ov_lt_lsl"],
      b["exp_ov_gt_usl"],
      b["exp_ov_total"],
      b["exp_wi_lt_lsl"],
      b["exp_wi_gt_usl"],
      b["exp_wi_total"],
      b["lsl"],
      b["target"],
      b["usl"],
      title_str,
      w_in,
      h_in,
      show_outer_border,
  )


@st.cache_data(show_spinner=False, max_entries=16)
def cached_box_png(
    data_fp,
    box_labels,
    box_arrays,
    p_lsl,
    p_target,
    p_usl,
    title_str,
    w_in,
    h_in,
    show_outliers,
    show_median_val,
    show_mean_val,
    decimals,
    show_outer_border,
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=150)
  box_data = [
      arr if len(arr) > 0 else np.array([p_target], dtype=np.float32)
      for arr in box_arrays
  ]
  n_boxes = len(box_data)
  box_width = 0.42 if n_boxes <= 15 else 0.36

  ax.boxplot(
      box_data,
      tick_labels=list(box_labels),
      patch_artist=True,
      showfliers=show_outliers,
      widths=box_width,
      boxprops=dict(facecolor="#78A2CC", edgecolor="#2B4C7E", linewidth=1.0),
      medianprops=dict(color="#111827", linewidth=1.3),
      whiskerprops=dict(color="#2B4C7E", linewidth=1.0),
      capprops=dict(color="#2B4C7E", linewidth=1.0),
  )

  ax.axhline(p_usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(p_target, color="#DC2626", ls="--", lw=1.0, alpha=0.75)
  ax.axhline(p_lsl, color="#DC2626", ls="--", lw=1.2)

  width_scale = min(w_in / 11.0, 1.15)
  if show_median_val or show_mean_val:
    label_font_size = (
        (8.2 if n_boxes <= 12 else (7.0 if n_boxes <= 22 else 6.0))
        * width_scale
    )
    x_offset = box_width * 0.54
    fmt_str = f"{{:.{decimals}f}}"
    y_min_cur, y_max_cur = ax.get_ylim()
    y_span_cur = max(y_max_cur - y_min_cur, 1e-6)

    for idx, arr in enumerate(box_data):
      x_pos = (idx + 1) + x_offset
      med_v = float(np.median(arr)) if show_median_val else None
      mean_v = float(np.mean(arr)) if show_mean_val else None

      if show_median_val and show_mean_val:
        min_gap = y_span_cur * 0.032
        y_med_txt, y_mean_txt = med_v, mean_v
        if abs(y_mean_txt - y_med_txt) < min_gap:
          if y_mean_txt >= y_med_txt:
            y_mean_txt = med_v + min_gap * 0.6
            y_med_txt = med_v - min_gap * 0.6
          else:
            y_mean_txt = med_v - min_gap * 0.6
            y_med_txt = med_v + min_gap * 0.6
        ax.text(
            x_pos,
            y_med_txt,
            f"Med:{fmt_str.format(med_v)}",
            va="center",
            ha="left",
            fontsize=label_font_size,
            color="#1F2937",
        )
        ax.text(
            x_pos,
            y_mean_txt,
            f"Avg:{fmt_str.format(mean_v)}",
            va="center",
            ha="left",
            fontsize=label_font_size,
            color="#1D4ED8",
        )
      elif show_median_val:
        ax.text(
            x_pos,
            med_v,
            fmt_str.format(med_v),
            va="center",
            ha="left",
            fontsize=label_font_size,
            color="#1F2937",
        )
      elif show_mean_val:
        ax.text(
            x_pos,
            mean_v,
            fmt_str.format(mean_v),
            va="center",
            ha="left",
            fontsize=label_font_size,
            color="#1D4ED8",
        )
    ax.set_xlim(0.4, n_boxes + 1.05)

  ax_r = ax.twinx()
  ax_r.set_ylim(ax.get_ylim())
  ax_r.set_yticks([p_lsl, p_target, p_usl])
  ax_r.set_yticklabels(
      [f"{p_lsl}", f"{p_target}", f"{p_usl}"],
      color="#B91C1C",
      fontsize=8.8,
      fontweight="bold",
  )

  ax.set_title(
      title_str,
      fontsize=max(11.5, 13.5 * width_scale),
      fontweight="bold",
      pad=12,
      fontproperties=FONT_PROP,
  )
  ax.set_ylabel("Value", fontsize=10)
  ax.tick_params(
      axis="x", rotation=45 if len(box_labels) > 5 else 0, labelsize=8.8
  )
  for lbl in ax.get_xticklabels():
    lbl.set_fontproperties(FONT_PROP)
  ax.grid(True, ls=":", alpha=0.45)
  plt.tight_layout(pad=1.2)
  return save_fig_with_border(fig, show_outer_border, use_tight=False)


def render_box_from_bundle(
    b,
    title_str,
    w_in,
    h_in,
    show_outliers,
    show_median_val,
    show_mean_val,
    decimals,
    show_outer_border,
):
  df_c = b["df_clean"]
  p_cols = b["cols"]
  box_labels = tuple(str(c) for c in p_cols)
  box_arrays = tuple(
      df_c[c].dropna().to_numpy(dtype=np.float32) for c in p_cols
  )
  return cached_box_png(
      b["fp"],
      box_labels,
      box_arrays,
      b["lsl"],
      b["target"],
      b["usl"],
      title_str,
      w_in,
      h_in,
      show_outliers,
      show_median_val,
      show_mean_val,
      decimals,
      show_outer_border,
  )


@st.cache_data(show_spinner=False, max_entries=16)
def cached_time_series_png(
    data_fp,
    x_seq,
    x_label_text,
    col_names,
    y_series_tuple,
    p_lsl,
    p_target,
    p_usl,
    title_str,
    w_in,
    h_in,
    y_mode_opt,
    ymin_val,
    ymax_val,
    show_outer_border,
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=150)
  markers = ["o", "s", "D", "^", "v", "<", ">", "p", "*", "h"]
  cmap = plt.get_cmap("tab20")
  step_mark = max(1, len(x_seq) // 200)

  for idx, (col_name, y_col) in enumerate(zip(col_names, y_series_tuple)):
    ax.plot(
        x_seq,
        y_col,
        color=cmap(idx % 20),
        lw=1.1,
        marker=markers[idx % len(markers)],
        markersize=3.2,
        markevery=step_mark,
        alpha=0.85,
        label=str(col_name),
    )

  ax.axhline(p_usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(p_target, color="#DC2626", ls="--", lw=1.0, alpha=0.75)
  ax.axhline(p_lsl, color="#DC2626", ls="--", lw=1.2)

  if (
      y_mode_opt == "自定义范围 (Manual)"
      and ymin_val is not None
      and ymax_val is not None
      and ymin_val < ymax_val
  ):
    ax.set_ylim(ymin_val, ymax_val)

  width_scale = min(w_in / 11.0, 1.15)
  ax.set_title(
      title_str,
      fontsize=max(11.5, 13.5 * width_scale),
      fontweight="bold",
      pad=12,
      fontproperties=FONT_PROP,
  )
  ax.set_xlabel(x_label_text, fontsize=10)
  ax.set_ylabel("Value", fontsize=10)
  ax.grid(True, ls=":", alpha=0.45)

  handles, labels_ts = ax.get_legend_handles_labels()
  if w_in / h_in < 1.55:
    n_cols_leg = min(5, max(3, len(handles[:20]) // 3))
    ax.legend(
        handles[:20],
        labels_ts[:20],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=n_cols_leg,
        prop=FONT_PROP,
        fontsize=7.6,
        frameon=True,
    )
  else:
    leg = ax.legend(
        handles[:20],
        labels_ts[:20],
        title="Variables" if len(handles) <= 20 else "Variables (Top 20)",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        prop=FONT_PROP,
        fontsize=8.0,
    )
    leg.get_title().set_fontsize(8.8)

  plt.tight_layout(pad=1.0)
  return save_fig_with_border(fig, show_outer_border, use_tight=True)


def render_time_series_from_bundle(
    b,
    title_str,
    w_in,
    h_in,
    x_mode_opt,
    y_mode_opt,
    ymin_val,
    ymax_val,
    show_outer_border,
    max_pts=4000,
):
  df_c = b["df_clean"]
  p_cols = b["cols"]
  if x_mode_opt == "保留原始表格行号 (Row Index)":
    x_seq = df_c["Row_Index"].to_numpy(dtype=np.int32)
    x_label_text = "Original Row Index"
  else:
    x_seq = np.arange(1, len(df_c) + 1, dtype=np.int32)
    x_label_text = "Filtered Sequence Index (1..N)"

  if len(x_seq) > max_pts:
    step = max(1, len(x_seq) // max_pts)
    x_seq_sub = x_seq[::step]
    y_tuple = tuple(
        df_c[c].to_numpy(dtype=np.float32)[::step] for c in p_cols
    )
  else:
    x_seq_sub = x_seq
    y_tuple = tuple(df_c[c].to_numpy(dtype=np.float32) for c in p_cols)

  return cached_time_series_png(
      b["fp"],
      x_seq_sub,
      x_label_text,
      tuple(p_cols),
      y_tuple,
      b["lsl"],
      b["target"],
      b["usl"],
      title_str,
      w_in,
      h_in,
      y_mode_opt,
      ymin_val,
      ymax_val,
      show_outer_border,
  )


@st.cache_data(show_spinner=False, max_entries=16)
def cached_scatter_series_png(
    data_fp,
    x_seq,
    x_label_text,
    col_names,
    y_series_tuple,
    p_lsl,
    p_target,
    p_usl,
    title_str,
    w_in,
    h_in,
    y_mode_opt,
    ymin_val,
    ymax_val,
    point_size,
    show_outer_border,
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=150)
  n_pts = len(x_seq)
  if point_size is None:
    pt_s = 4.5 if n_pts > 5000 else (7.0 if n_pts > 1500 else 11.0)
  else:
    pt_s = float(point_size)

  markers = ["o", "s", "D", "^", "v", "<", ">", "p", "*", "h"]
  cmap = plt.get_cmap("tab20")

  for idx, (col_name, y_col) in enumerate(zip(col_names, y_series_tuple)):
    ax.scatter(
        x_seq,
        y_col,
        color=cmap(idx % 20),
        marker=markers[idx % len(markers)],
        s=pt_s,
        alpha=0.72,
        edgecolors="none",
        label=str(col_name),
    )

  ax.axhline(p_usl, color="#DC2626", ls="--", lw=1.2)
  ax.axhline(p_target, color="#DC2626", ls="--", lw=1.0, alpha=0.75)
  ax.axhline(p_lsl, color="#DC2626", ls="--", lw=1.2)

  if (
      y_mode_opt == "自定义范围 (Manual)"
      and ymin_val is not None
      and ymax_val is not None
      and ymin_val < ymax_val
  ):
    ax.set_ylim(ymin_val, ymax_val)

  width_scale = min(w_in / 11.0, 1.15)
  ax.set_title(
      title_str,
      fontsize=max(11.5, 13.5 * width_scale),
      fontweight="bold",
      pad=12,
      fontproperties=FONT_PROP,
  )
  ax.set_xlabel(x_label_text, fontsize=10)
  ax.set_ylabel("Value", fontsize=10)
  ax.grid(True, ls=":", alpha=0.45)

  handles, labels_sc = ax.get_legend_handles_labels()
  if w_in / h_in < 1.55:
    n_cols_leg = min(5, max(3, len(handles[:20]) // 3))
    ax.legend(
        handles[:20],
        labels_sc[:20],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=n_cols_leg,
        prop=FONT_PROP,
        fontsize=7.6,
        frameon=True,
    )
  else:
    leg = ax.legend(
        handles[:20],
        labels_sc[:20],
        title="Variables" if len(handles) <= 20 else "Variables (Top 20)",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        prop=FONT_PROP,
        fontsize=8.0,
    )
    leg.get_title().set_fontsize(8.8)

  plt.tight_layout(pad=1.0)
  return save_fig_with_border(fig, show_outer_border, use_tight=True)


def render_scatter_from_bundle(
    b,
    title_str,
    w_in,
    h_in,
    x_mode_opt,
    y_mode_opt,
    ymin_val,
    ymax_val,
    point_size,
    show_outer_border,
    max_pts=4000,
):
  df_c = b["df_clean"]
  p_cols = b["cols"]
  if x_mode_opt == "保留原始表格行号 (Row Index)":
    x_seq = df_c["Row_Index"].to_numpy(dtype=np.int32)
    x_label_text = "Original Row Index"
  else:
    x_seq = np.arange(1, len(df_c) + 1, dtype=np.int32)
    x_label_text = "Filtered Sequence Index (1..N)"

  if len(x_seq) > max_pts:
    step = max(1, len(x_seq) // max_pts)
    x_seq_sub = x_seq[::step]
    y_tuple = tuple(
        df_c[c].to_numpy(dtype=np.float32)[::step] for c in p_cols
    )
  else:
    x_seq_sub = x_seq
    y_tuple = tuple(df_c[c].to_numpy(dtype=np.float32) for c in p_cols)

  return cached_scatter_series_png(
      b["fp"],
      x_seq_sub,
      x_label_text,
      tuple(p_cols),
      y_tuple,
      b["lsl"],
      b["target"],
      b["usl"],
      title_str,
      w_in,
      h_in,
      y_mode_opt,
      ymin_val,
      ymax_val,
      point_size,
      show_outer_border,
  )


@st.cache_data(show_spinner=False, max_entries=16)
def cached_row_mean_png(
    data_fp,
    x_seq,
    y_mean_series,
    p_lsl,
    p_target,
    p_usl,
    title_str,
    w_in,
    h_in,
    y_mode_opt,
    ymin_val,
    ymax_val,
    show_outer_border,
):
  fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=150)
  ax.set_facecolor("white")

  ax.plot(
      x_seq,
      np.full_like(x_seq, p_target, dtype=np.float32),
      color="#4472C4",
      lw=2.5,
      label="目标值",
  )
  ax.plot(
      x_seq,
      np.full_like(x_seq, p_usl, dtype=np.float32),
      color="#ED7D31",
      lw=2.5,
      label="规格上限",
  )
  ax.plot(
      x_seq,
      np.full_like(x_seq, p_lsl, dtype=np.float32),
      color="#A5A5A5",
      lw=2.5,
      label="规格下限",
  )
  ax.plot(
      x_seq,
      y_mean_series,
      color="#FFC000",
      lw=2.2,
      label="平均值",
  )

  if (
      y_mode_opt == "自定义范围 (Manual)"
      and ymin_val is not None
      and ymax_val is not None
      and ymin_val < ymax_val
  ):
    ax.set_ylim(ymin_val, ymax_val)
  else:
    spec_span = max(p_usl - p_lsl, 1e-6)
    y_low = min(
        p_lsl - 0.5 * spec_span,
        float(np.min(y_mean_series)) - 0.15 * spec_span,
    )
    y_high = max(
        p_usl + 0.25 * spec_span,
        float(np.max(y_mean_series)) + 0.15 * spec_span,
    )
    ax.set_ylim(y_low, y_high)

  if len(x_seq) >= 2 and x_seq[-1] > x_seq[0]:
    ax.set_xlim(x_seq[0], x_seq[-1])

  if len(x_seq) > 1:
    n_ticks = max(12, int(w_in * 2.1))
    tick_step = max(1, len(x_seq) // n_ticks)
    tick_positions = x_seq[::tick_step]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(
        [str(v) for v in tick_positions],
        rotation=90,
        fontsize=9.0,
        color="#595959",
    )

  ax.tick_params(axis="y", labelsize=9.5, colors="#595959", length=0)
  ax.tick_params(axis="x", length=0, pad=5)
  ax.yaxis.grid(True, linestyle="-", linewidth=0.8, color="#D9D9D9")
  ax.spines["top"].set_visible(False)
  ax.spines["right"].set_visible(False)
  ax.spines["left"].set_visible(False)

  width_scale = min(w_in / 10.5, 1.15)
  ax.set_title(
      title_str,
      fontsize=max(13.5, 16.5 * width_scale),
      fontweight="normal",
      color="#595959",
      pad=16,
      fontproperties=FONT_PROP,
  )

  leg = ax.legend(
      loc="upper center",
      bbox_to_anchor=(0.5, -0.14),
      ncol=4,
      frameon=False,
      prop=FONT_PROP,
      fontsize=10.5,
      handlelength=2.2,
      columnspacing=1.8,
  )
  for text in leg.get_texts():
    text.set_color("#595959")

  plt.tight_layout(pad=1.0)
  return save_fig_with_border(fig, show_outer_border, use_tight=True)


def render_row_mean_from_bundle(
    b,
    title_str,
    w_in,
    h_in,
    x_mode_opt,
    y_mode_opt,
    ymin_val,
    ymax_val,
    show_outer_border,
    max_pts=4000,
):
  df_c = b["df_clean"]
  if x_mode_opt == "保留原始表格行号 (Row Index)":
    x_seq = df_c["Row_Index"].to_numpy(dtype=np.int32)
  else:
    x_seq = np.arange(1, len(df_c) + 1, dtype=np.int32)
  y_mean_series = df_c["_Row_Mean_"].to_numpy(dtype=np.float32)

  if len(x_seq) > max_pts:
    step = max(1, len(x_seq) // max_pts)
    x_seq = x_seq[::step]
    y_mean_series = y_mean_series[::step]

  return cached_row_mean_png(
      b["fp"],
      x_seq,
      y_mean_series,
      b["lsl"],
      b["target"],
      b["usl"],
      title_str,
      w_in,
      h_in,
      y_mode_opt,
      ymin_val,
      ymax_val,
      show_outer_border,
  )


@st.cache_data(show_spinner=False, max_entries=12)
def cached_grouped_histogram_png(
    batch_summary_tuple,
    p_lsl,
    p_target,
    p_usl,
    title_str,
    bins_num,
    y_metric,
    show_normal_fit,
    show_spec_lines,
    show_outer_border,
):
  fig, ax = plt.subplots(figsize=(11.5, 5.8), dpi=150)
  ax.set_facecolor("white")

  all_concat = np.concatenate([item[1] for item in batch_summary_tuple])
  x_min_d, x_max_d = float(np.min(all_concat)), float(np.max(all_concat))
  if x_max_d <= x_min_d:
    x_max_d = x_min_d + 1.0
  bin_edges = np.linspace(x_min_d, x_max_d, int(bins_num) + 1)
  bin_width = bin_edges[1] - bin_edges[0]
  is_density = "密度" in y_metric

  max_y_val = 1.0
  x_curve = np.linspace(
      min(x_min_d, p_lsl if show_spec_lines else x_min_d) - 0.5 * bin_width,
      max(x_max_d, p_usl if show_spec_lines else x_max_d) + 0.5 * bin_width,
      360,
  )

  for idx, (lbl, vals, s_mean, s_ov) in enumerate(batch_summary_tuple):
    col_fill = BATCH_COLORS[idx % len(BATCH_COLORS)]
    col_edge = BATCH_EDGE_COLORS[idx % len(BATCH_EDGE_COLORS)]

    counts_arr, _, _ = ax.hist(
        vals,
        bins=bin_edges,
        density=is_density,
        color=col_fill,
        edgecolor=col_edge,
        linewidth=0.75,
        alpha=0.46,
        label=f"{lbl} (N={len(vals)}, μ={s_mean:.3f})",
    )
    if len(counts_arr) > 0:
      max_y_val = max(max_y_val, float(np.max(counts_arr)))

    if show_normal_fit and len(vals) >= 2 and s_ov > 1e-12:
      pdf_y = stats.norm.pdf(x_curve, s_mean, s_ov)
      curve_y = pdf_y if is_density else pdf_y * len(vals) * bin_width
      max_y_val = max(max_y_val, float(np.max(curve_y)))
      ax.plot(
          x_curve,
          curve_y,
          color=col_edge,
          lw=1.8,
          ls="-",
          alpha=0.92,
          label=f"{lbl} 正态拟合 (σ={s_ov:.4f})",
      )

  if show_spec_lines:
    ax.axvline(
        p_lsl, color="#DC2626", ls="--", lw=1.25, label=f"LSL ({p_lsl})"
    )
    ax.axvline(
        p_target,
        color="#16A34A",
        ls="-.",
        lw=1.1,
        label=f"Target ({p_target})",
    )
    ax.axvline(
        p_usl, color="#DC2626", ls="--", lw=1.25, label=f"USL ({p_usl})"
    )

  ax.set_ylim(0, max_y_val * 1.12)
  ax.set_title(
      title_str,
      fontsize=13,
      fontweight="bold",
      pad=12,
      fontproperties=FONT_PROP,
  )
  ax.set_xlabel("数据", fontsize=10, fontproperties=FONT_PROP)
  ax.set_ylabel(
      "概率密度" if is_density else "频数",
      fontsize=10,
      fontproperties=FONT_PROP,
  )
  ax.tick_params(axis="both", labelsize=9, colors="#475569")
  ax.grid(True, ls=":", alpha=0.45, color="#CBD5E1")
  ax.spines["top"].set_visible(False)
  ax.spines["right"].set_visible(False)

  ax.legend(
      prop=FONT_PROP,
      fontsize=8.2,
      loc="upper right",
      frameon=True,
      facecolor="white",
      edgecolor="#E2E8F0",
  )
  plt.tight_layout()
  return save_fig_with_border(fig, show_outer_border, use_tight=True)


def render_grouped_histogram_from_map(
    batch_labels_all,
    p_batch_map,
    title_str,
    bins_num,
    y_metric,
    show_normal_fit,
    show_spec_lines,
    show_outer_border,
):
  active = [lbl for lbl in batch_labels_all if lbl in p_batch_map]
  first_b = p_batch_map[active[0]]
  summary_tuple = tuple(
      (
          lbl,
          p_batch_map[lbl]["all_valid_vals"],
          p_batch_map[lbl]["sample_mean"],
          p_batch_map[lbl]["std_overall"],
      )
      for lbl in active
  )
  return cached_grouped_histogram_png(
      summary_tuple,
      first_b["lsl"],
      first_b["target"],
      first_b["usl"],
      title_str,
      bins_num,
      y_metric,
      show_normal_fit,
      show_spec_lines,
      show_outer_border,
  )


@st.cache_data(show_spinner=False, max_entries=12)
def cached_multi_batch_comparison_png(
    batch_stats_tuple, p_lsl, p_target, p_usl, title_str, show_outer_border
):
  fig = plt.figure(figsize=(12.2, 6.2), dpi=150)
  gs = fig.add_gridspec(1, 2, width_ratios=[2.2, 1.25], wspace=0.25)
  ax_dist = fig.add_subplot(gs[0, 0])
  ax_kpi = fig.add_subplot(gs[0, 1])

  span = max(p_usl - p_lsl, 1e-6)
  all_concat = np.concatenate([item[1] for item in batch_stats_tuple])
  x_min = min(p_lsl - 0.15 * span, float(np.min(all_concat)) - 0.05 * span)
  x_max = max(p_usl + 0.15 * span, float(np.max(all_concat)) + 0.05 * span)
  x_grid = np.linspace(x_min, x_max, 360)

  for idx, (lbl, _, s_mean, s_ov, cpk_v, _) in enumerate(batch_stats_tuple):
    col = BATCH_COLORS[idx % len(BATCH_COLORS)]
    if s_ov > 1e-12:
      ax_dist.plot(
          x_grid,
          stats.norm.pdf(x_grid, s_mean, s_ov),
          color=col,
          lw=2.0,
          label=f"{lbl} (CPK={cpk_v:.2f}, μ={s_mean:.3f})",
      )
    ax_dist.axvline(s_mean, color=col, ls=":", lw=1.1, alpha=0.8)

  ax_dist.axvline(p_lsl, color="#DC2626", ls="--", lw=1.3)
  ax_dist.axvline(p_usl, color="#DC2626", ls="--", lw=1.3)
  ax_dist.axvline(p_target, color="#16A34A", ls="-.", lw=1.1)

  y_top = ax_dist.get_ylim()[1]
  ax_dist.text(
      p_lsl,
      y_top * 0.98,
      f"LSL {p_lsl}",
      color="#B91C1C",
      ha="center",
      va="top",
      fontsize=8.2,
      fontweight="bold",
  )
  ax_dist.text(
      p_usl,
      y_top * 0.98,
      f"USL {p_usl}",
      color="#B91C1C",
      ha="center",
      va="top",
      fontsize=8.2,
      fontweight="bold",
  )
  ax_dist.text(
      p_target,
      y_top * 0.98,
      f"Tgt {p_target}",
      color="#15803D",
      ha="center",
      va="top",
      fontsize=8.2,
  )

  ax_dist.set_title(
      "各批次正态分布与中心偏移对比",
      fontsize=10.5,
      fontproperties=FONT_PROP,
  )
  ax_dist.set_xlabel("测量值", fontsize=9.5, fontproperties=FONT_PROP)
  ax_dist.set_ylabel("概率密度", fontsize=9.5, fontproperties=FONT_PROP)
  ax_dist.legend(prop=FONT_PROP, fontsize=8.0, loc="upper left")
  ax_dist.grid(True, ls=":", alpha=0.45)

  labels_only = [item[0] for item in batch_stats_tuple]
  cpk_vals = [item[4] for item in batch_stats_tuple]
  ppk_vals = [item[5] for item in batch_stats_tuple]
  x_pos = np.arange(len(labels_only))
  bar_w = 0.34

  bars1 = ax_kpi.bar(
      x_pos - bar_w / 2,
      cpk_vals,
      width=bar_w,
      color="#2563EB",
      label="CPK (组内)",
  )
  bars2 = ax_kpi.bar(
      x_pos + bar_w / 2,
      ppk_vals,
      width=bar_w,
      color="#93C5FD",
      edgecolor="#1D4ED8",
      label="PPK (整体)",
  )
  ax_kpi.axhline(1.33, color="#16A34A", ls="--", lw=1.1, label="基准 1.33")
  ax_kpi.axhline(1.00, color="#DC2626", ls=":", lw=1.0, label="警戒 1.00")

  for br in list(bars1) + list(bars2):
    h_val = br.get_height()
    if np.isfinite(h_val):
      ax_kpi.text(
          br.get_x() + br.get_width() / 2,
          h_val + 0.03,
          f"{h_val:.2f}",
          ha="center",
          va="bottom",
          fontsize=7.8,
      )

  ax_kpi.set_xticks(x_pos)
  ax_kpi.set_xticklabels(
      [lbl.split(":")[0] for lbl in labels_only],
      fontsize=8.8,
      fontproperties=FONT_PROP,
  )
  ax_kpi.set_ylim(0, max(1.8, float(np.nanmax(cpk_vals + ppk_vals)) * 1.22))
  ax_kpi.set_title("各批次过程能力指数对比", fontsize=10.5, fontproperties=FONT_PROP)
  ax_kpi.legend(prop=FONT_PROP, fontsize=7.6, loc="upper right")
  ax_kpi.grid(True, axis="y", ls=":", alpha=0.45)

  fig.suptitle(
      title_str,
      fontsize=13,
      fontweight="bold",
      y=0.98,
      fontproperties=FONT_PROP,
  )
  plt.tight_layout(rect=[0, 0, 1, 0.93])
  return save_fig_with_border(fig, show_outer_border, use_tight=True)


def render_multi_batch_comparison_from_map(
    batch_labels_all, p_batch_map, title_str, show_outer_border
):
  active = [lbl for lbl in batch_labels_all if lbl in p_batch_map]
  first_b = p_batch_map[active[0]]
  stats_tuple = tuple(
      (
          lbl,
          p_batch_map[lbl]["all_valid_vals"],
          p_batch_map[lbl]["sample_mean"],
          p_batch_map[lbl]["std_overall"],
          p_batch_map[lbl]["cpk"],
          p_batch_map[lbl]["ppk"],
      )
      for lbl in active
  )
  return cached_multi_batch_comparison_png(
      stats_tuple,
      first_b["lsl"],
      first_b["target"],
      first_b["usl"],
      title_str,
      show_outer_border,
  )


@st.cache_data(show_spinner=False, max_entries=12)
def cached_multi_batch_mean_trend_png(
    batch_trends_tuple, p_lsl, p_target, p_usl, title_str, show_outer_border
):
  fig, ax = plt.subplots(figsize=(12.8, 5.4), dpi=150)
  max_len = 1
  for idx, (lbl, y_m) in enumerate(batch_trends_tuple):
    x_s = np.arange(1, len(y_m) + 1, dtype=np.int32)
    max_len = max(max_len, len(y_m))
    ax.plot(
        x_s,
        y_m,
        color=BATCH_COLORS[idx % len(BATCH_COLORS)],
        lw=1.8,
        alpha=0.88,
        label=lbl,
    )

  ax.axhline(
      p_usl, color="#DC2626", ls="--", lw=1.2, label=f"USL ({p_usl})"
  )
  ax.axhline(
      p_target, color="#16A34A", ls="-.", lw=1.1, label=f"Target ({p_target})"
  )
  ax.axhline(
      p_lsl, color="#DC2626", ls="--", lw=1.2, label=f"LSL ({p_lsl})"
  )

  ax.set_xlim(1, max(2, max_len))
  ax.set_title(
      title_str, fontsize=12.5, fontweight="bold", fontproperties=FONT_PROP
  )
  ax.set_xlabel(
      "区间内样本序号 (1..N)", fontsize=9.5, fontproperties=FONT_PROP
  )
  ax.set_ylabel("行均值", fontsize=9.5, fontproperties=FONT_PROP)
  ax.grid(True, ls=":", alpha=0.45)
  ax.legend(prop=FONT_PROP, fontsize=8.2, ncol=min(5, len(batch_trends_tuple) + 3))
  plt.tight_layout()
  return save_fig_with_border(fig, show_outer_border, use_tight=True)


def render_multi_batch_mean_trend_from_map(
    batch_labels_all, p_batch_map, title_str, show_outer_border, max_pts=4000
):
  active = [lbl for lbl in batch_labels_all if lbl in p_batch_map]
  first_b = p_batch_map[active[0]]
  trends_list = []
  for lbl in active:
    y_m = p_batch_map[lbl]["df_clean"]["_Row_Mean_"].to_numpy(dtype=np.float32)
    if len(y_m) > max_pts:
      step = max(1, len(y_m) // max_pts)
      y_m = y_m[::step]
    trends_list.append((lbl, y_m))
  return cached_multi_batch_mean_trend_png(
      tuple(trends_list),
      first_b["lsl"],
      first_b["target"],
      first_b["usl"],
      title_str,
      show_outer_border,
  )


# ==============================================================================
#                   版本 1.0：单批 / 多同表头批次纵向堆叠分析
# ==============================================================================
def run_v1_app():
  render_sidebar_mode_switcher("v1")

  def render_v1_header(stacked_info_text=None):
    st.markdown(
        "<span style='background:#475569;color:#fff;font-size:11px;font-weight:700;"
        "padding:2px 9px;border-radius:999px;'>v1.0 · 单批 / 多批叠加合并分析</span>",
        unsafe_allow_html=True,
    )
    st.title("在线检测 SPC 与过程能力分析系统")
    st.caption("Created by xu")
    if stacked_info_text:
      st.markdown(
          f"<div style='border-left:4px solid #475569;background:rgba(71,85,105,0.07);"
          f"padding:8px 13px;border-radius:0 8px 8px 0;margin:6px 0 12px 0;font-size:13px;'>"
          f"<strong>多批次堆叠合并状态：</strong>{stacked_info_text}</div>",
          unsafe_allow_html=True,
      )

  st.sidebar.header("1️⃣ 数据源与多项目分组")
  uploaded_files = st.sidebar.file_uploader(
      "上传检测数据表（支持单文件或多同表头批次堆叠）",
      type=["xlsx", "xls", "csv"],
      accept_multiple_files=True,
      key="v1_uploader",
  )

  if not uploaded_files:
    render_v1_header()
    st.info(
        "👈 请在左侧边栏上传检测数据表格（单文件或表头相同的多个批次文件；上传多个文件时将自动往下堆叠合并分析）。"
    )
    st.stop()

  file_sheets_list = []
  for f_idx, up_f in enumerate(uploaded_files):
    try:
      s_dict = load_workbook_sheets(up_f.getvalue(), up_f.name)
    except Exception as exc:
      st.error(f"❌ 文件 [{up_f.name}] 读取失败，请检查文件格式或编码：{exc}")
      st.stop()
    file_sheets_list.append({
        "idx": f_idx,
        "name": up_f.name,
        "sheets": s_dict,
    })

  common_sheet_names = [
      sh
      for sh in file_sheets_list[0]["sheets"].keys()
      if all(sh in item["sheets"] for item in file_sheets_list[1:])
  ]
  sheet_options = (
      common_sheet_names
      if common_sheet_names
      else list(file_sheets_list[0]["sheets"].keys())
  )

  selected_sheet = st.sidebar.selectbox(
      "工作表 (Sheet)", sheet_options, key="v1_sheet_sel"
  )

  stacked_parts = []
  used_sources = []
  for item in file_sheets_list:
    s_map = item["sheets"]
    if selected_sheet in s_map:
      part_df = s_map[selected_sheet].copy()
      actual_sh = selected_sheet
    else:
      fallback_sh = list(s_map.keys())[0]
      part_df = s_map[fallback_sh].copy()
      actual_sh = fallback_sh

    part_df = part_df.dropna(how="all")
    if part_df.empty:
      continue

    src_label = (
        item["name"]
        if len(s_map) == 1
        else f"{item['name']} [{actual_sh}]"
    )
    part_df["Source_Batch"] = src_label
    stacked_parts.append(part_df)
    used_sources.append(f"{src_label} ({len(part_df)}行)")

  if not stacked_parts:
    st.error("所选工作表无有效数据，请检查表格内容。")
    st.stop()

  df_raw = pd.concat(stacked_parts, ignore_index=True)
  df_raw = df_raw.dropna(how="all").reset_index(drop=True)
  del stacked_parts

  if df_raw.empty:
    st.error("堆叠合并后无有效数据，请检查表格内容。")
    st.stop()

  df_raw.insert(0, "Row_Index", np.arange(1, len(df_raw) + 1, dtype=np.int32))

  stacked_banner = None
  if len(used_sources) > 1:
    stacked_banner = (
        f"已将 <strong>{len(used_sources)} 个批次/文件</strong> 往下堆叠合并，"
        f"合计 <strong>{len(df_raw)} 行</strong>（{' → '.join(used_sources)}）。"
    )

  numeric_cols_all = []
  for col in df_raw.columns:
    if col in ("Row_Index", "Source_Batch"):
      continue
    converted = pd.to_numeric(df_raw[col], errors="coerce")
    non_null = df_raw[col].notna().sum()
    if non_null > 0 and converted.notna().sum() / non_null >= 0.3:
      df_raw[col] = converted.astype(np.float32)
      numeric_cols_all.append(col)

  if not numeric_cols_all:
    st.error("未识别到有效的数值型检测列，请检查表格格式（需第1行为表头）。")
    st.stop()

  spec_info = detect_spec_from_columns(df_raw, df_raw.columns)
  measurement_candidates = [
      c for c in numeric_cols_all if c not in spec_info["spec_cols"]
  ]
  if not measurement_candidates:
    measurement_candidates = numeric_cols_all

  group_order, inferred_groups = infer_parameter_groups(measurement_candidates)
  suggested_default_groups = [
      g for g in group_order if not is_likely_non_measurement(g)
  ]

  files_sig = "||".join(
      f"{it['name']}:{len(it['sheets'])}" for it in file_sheets_list
  )
  dataset_key = f"{files_sig}::{selected_sheet}::{len(df_raw)}"

  if st.session_state.get("v1_active_dataset_key") != dataset_key:
    st.session_state["v1_active_dataset_key"] = dataset_key
    st.session_state["v1_project_groups_map"] = {
        k: list(v) for k, v in inferred_groups.items()
    }
    st.session_state["v1_draft_projects"] = list(suggested_default_groups)
    st.session_state["v1_confirmed_projects"] = list(suggested_default_groups)
    st.session_state["v1_confirmed_groups_snapshot"] = {
        k: list(v) for k, v in inferred_groups.items()
    }
    st.session_state["v1_selection_dirty"] = False
    st.session_state["v1_project_specs_map"] = {}
    st.session_state["v1_draft_specs_map"] = {}
    st.session_state["v1_spec_dirty"] = False

  proj_map = st.session_state.setdefault(
      "v1_project_groups_map", {k: list(v) for k, v in inferred_groups.items()}
  )
  available_proj_names = list(proj_map.keys())

  draft_default = [
      p
      for p in st.session_state.get(
          "v1_draft_projects", suggested_default_groups
      )
      if p in available_proj_names
  ]

  selected_projects = st.sidebar.multiselect(
      "待生成项目 / 参数组（已自动排除日期/编号等列）",
      options=available_proj_names,
      default=draft_default,
      key=f"v1_ms_draft_projects_{dataset_key}",
  )
  st.session_state["v1_draft_projects"] = selected_projects

  cols_changed_in_expander = False
  with st.sidebar.expander("🔧 调整各项目包含的通道列", expanded=False):
    for p_name in available_proj_names:
      updated_cols = st.multiselect(
          f"[{p_name}] 通道列",
          options=numeric_cols_all,
          default=[c for c in proj_map[p_name] if c in numeric_cols_all],
          key=f"v1_cols_for_{dataset_key}_{p_name}",
      )
      if updated_cols and updated_cols != proj_map[p_name]:
        proj_map[p_name] = updated_cols
        cols_changed_in_expander = True

    new_grp_name = st.text_input(
        "新增自定义项目组名称",
        value="",
        placeholder="例如: 涂宽+白边对比",
        key=f"v1_new_grp_name_{dataset_key}",
    )
    new_grp_cols = st.multiselect(
        "选择新增项目组通道列",
        options=numeric_cols_all,
        default=[],
        key=f"v1_new_grp_cols_{dataset_key}",
    )
    if st.button(
        "➕ 添加项目组",
        key=f"v1_btn_add_grp_{dataset_key}",
        use_container_width=True,
    ):
      if new_grp_name.strip() and new_grp_cols:
        g_clean = new_grp_name.strip()
        proj_map[g_clean] = list(new_grp_cols)
        if g_clean not in st.session_state["v1_draft_projects"]:
          st.session_state["v1_draft_projects"].append(g_clean)
        st.session_state["v1_selection_dirty"] = True
        st.rerun()

  prev_confirmed = st.session_state.get("v1_confirmed_projects", [])
  prev_snapshot = st.session_state.get("v1_confirmed_groups_snapshot", {})
  current_selected_non_empty = [
      p for p in selected_projects if len(proj_map.get(p, [])) > 0
  ]
  current_snapshot = {
      p: list(proj_map.get(p, [])) for p in current_selected_non_empty
  }

  if (
      current_selected_non_empty != prev_confirmed
      or current_snapshot != prev_snapshot
      or cols_changed_in_expander
  ):
    st.session_state["v1_selection_dirty"] = True

  def compute_recommended_spec(df_src, cols_sel, s_info):
    vals = df_src[list(cols_sel)].to_numpy(dtype=np.float32)
    valid_v = vals[~np.isnan(vals)]
    if len(valid_v) > 0:
      mid = float(np.median(valid_v))
      mad = float(np.median(np.abs(valid_v - mid)))
      robust_std = mad * 1.4826 if mad > 0 else float(np.std(valid_v, ddof=1))
      half_tol = max(round(robust_std * 4.5, 4), 0.2) if robust_std > 0 else 1.0
    else:
      mid, half_tol = 0.0, 1.0

    rec_lsl = (
        s_info["lsl"] if s_info["lsl"] is not None else round(mid - half_tol, 4)
    )
    rec_usl = (
        s_info["usl"] if s_info["usl"] is not None else round(mid + half_tol, 4)
    )
    if s_info["target"] is not None:
      rec_target = s_info["target"]
    elif s_info["lsl"] is not None and s_info["usl"] is not None:
      rec_target = round((s_info["lsl"] + s_info["usl"]) / 2.0, 4)
    else:
      rec_target = round(mid, 4)
    return float(rec_lsl), float(rec_target), float(rec_usl)

  specs_map = st.session_state.setdefault("v1_project_specs_map", {})
  draft_specs_map = st.session_state.setdefault("v1_draft_specs_map", {})

  for p_name in current_selected_non_empty:
    p_key = f"{dataset_key}::{p_name}"
    if p_key not in specs_map:
      rl, rt, ru = compute_recommended_spec(df_raw, proj_map[p_name], spec_info)
      specs_map[p_key] = {"lsl": rl, "target": rt, "usl": ru}
    if p_key not in draft_specs_map:
      draft_specs_map[p_key] = dict(specs_map[p_key])

  def _sync_draft_spec(p_key, field_name, widget_key):
    draft_specs_map.setdefault(p_key, dict(specs_map.get(p_key, {})))
    draft_specs_map[p_key][field_name] = float(st.session_state[widget_key])
    st.session_state["v1_spec_dirty"] = True

  def _reestimate_v1_spec_callback(
      f_key, l_key, t_key, u_key, df_ref, cols_ref, sp_ref
  ):
    rl, rt, ru = compute_recommended_spec(df_ref, cols_ref, sp_ref)
    draft_specs_map[f_key] = {"lsl": rl, "target": rt, "usl": ru}
    st.session_state[l_key] = rl
    st.session_state[t_key] = rt
    st.session_state[u_key] = ru
    st.session_state["v1_spec_dirty"] = True

  generate_clicked = st.sidebar.button(
      "🚀 生成 / 更新所选项目图表",
      key=f"v1_btn_gen_charts_{dataset_key}",
      type="primary",
      use_container_width=True,
  )
  if generate_clicked:
    st.session_state["v1_confirmed_projects"] = list(current_selected_non_empty)
    st.session_state["v1_confirmed_groups_snapshot"] = {
        p: list(proj_map.get(p, [])) for p in current_selected_non_empty
    }
    st.session_state["v1_selection_dirty"] = False
    for p_name in current_selected_non_empty:
      p_key = f"{dataset_key}::{p_name}"
      if p_key in draft_specs_map:
        cand = draft_specs_map[p_key]
        if cand.get("lsl", 0.0) < cand.get("usl", 0.0):
          specs_map[p_key] = {
              "lsl": float(cand["lsl"]),
              "target": float(cand["target"]),
              "usl": float(cand["usl"]),
          }
    st.session_state["v1_spec_dirty"] = False

  if st.session_state.get("v1_selection_dirty", False):
    render_v1_header(stacked_banner)
    if not current_selected_non_empty:
      st.info(
          "👈 当前未选择任何项目。请在左侧**「待生成项目 / 参数组」**中选择项目，然后点击 **「🚀 生成 / 更新所选项目图表」**。"
      )
    else:
      st.warning(
          f"👈 检测到项目或通道列选择已变更（当前已选 {len(current_selected_non_empty)} 个项目：{', '.join(current_selected_non_empty)}）。已暂停自动出图，请点击左侧 **「🚀 生成 / 更新所选项目图表」** 开始生成。"
      )
    st.stop()

  confirmed_projects = [
      p
      for p in st.session_state.get("v1_confirmed_projects", [])
      if p in available_proj_names and len(proj_map.get(p, [])) > 0
  ]

  if not confirmed_projects:
    render_v1_header(stacked_banner)
    st.info(
        "👈 请在左侧**「待生成项目 / 参数组」**中选择至少一个项目，然后点击 **「🚀 生成 / 更新所选项目图表」**。"
    )
    st.stop()

  st.sidebar.header("2️⃣ 各项目 SPEC 规格")
  st.sidebar.caption("修改上下限或目标值时不会实时刷新图表，点上方按钮统一生效")

  current_focus_proj = st.sidebar.selectbox(
      "当前编辑 SPEC 的项目",
      options=confirmed_projects,
      index=0,
      key=f"v1_focus_spec_proj_{dataset_key}",
  )
  focus_key = f"{dataset_key}::{current_focus_proj}"
  cur_draft_spec = draft_specs_map.setdefault(
      focus_key, dict(specs_map[focus_key])
  )

  sc1, sc2, sc3 = st.sidebar.columns(3)
  lsl_w_key = f"v1_num_lsl_{focus_key}"
  tgt_w_key = f"v1_num_target_{focus_key}"
  usl_w_key = f"v1_num_usl_{focus_key}"

  st.session_state.setdefault(lsl_w_key, float(cur_draft_spec["lsl"]))
  st.session_state.setdefault(tgt_w_key, float(cur_draft_spec["target"]))
  st.session_state.setdefault(usl_w_key, float(cur_draft_spec["usl"]))

  sc1.number_input(
      "LSL",
      format="%.4f",
      key=lsl_w_key,
      on_change=_sync_draft_spec,
      args=(focus_key, "lsl", lsl_w_key),
  )
  sc2.number_input(
      "Target",
      format="%.4f",
      key=tgt_w_key,
      on_change=_sync_draft_spec,
      args=(focus_key, "target", tgt_w_key),
  )
  sc3.number_input(
      "USL",
      format="%.4f",
      key=usl_w_key,
      on_change=_sync_draft_spec,
      args=(focus_key, "usl", usl_w_key),
  )

  if float(draft_specs_map[focus_key]["lsl"]) >= float(
      draft_specs_map[focus_key]["usl"]
  ):
    st.sidebar.warning(f"⚠️ [{current_focus_proj}] LSL 应小于 USL，生效前请修正。")

  if st.session_state.get("v1_spec_dirty", False):
    st.sidebar.info("SPEC 已修改待生效：请点击上方「🚀 生成 / 更新所选项目图表」")

  st.sidebar.button(
      f"🔄 重新自动估算 [{current_focus_proj}] SPEC",
      key=f"v1_btn_reest_spec_{focus_key}",
      on_click=_reestimate_v1_spec_callback,
      args=(
          focus_key,
          lsl_w_key,
          tgt_w_key,
          usl_w_key,
          df_raw,
          proj_map[current_focus_proj],
          spec_info,
      ),
      use_container_width=True,
  )

  if len(confirmed_projects) > 1:
    with st.sidebar.expander("📋 批量查看/修改全部已生成项目 SPEC", expanded=False):
      for p_name in confirmed_projects:
        pk = f"{dataset_key}::{p_name}"
        d_sp = draft_specs_map.setdefault(pk, dict(specs_map[pk]))
        st.caption(f"**{p_name}**")
        b1, b2, b3 = st.columns(3)
        bl_k = f"v1_batch_lsl_{pk}"
        bt_k = f"v1_batch_tgt_{pk}"
        bu_k = f"v1_batch_usl_{pk}"
        st.session_state.setdefault(bl_k, float(d_sp["lsl"]))
        st.session_state.setdefault(bt_k, float(d_sp["target"]))
        st.session_state.setdefault(bu_k, float(d_sp["usl"]))
        b1.number_input(
            "LSL",
            format="%.4f",
            key=bl_k,
            on_change=_sync_draft_spec,
            args=(pk, "lsl", bl_k),
        )
        b2.number_input(
            "Target",
            format="%.4f",
            key=bt_k,
            on_change=_sync_draft_spec,
            args=(pk, "target", bt_k),
        )
        b3.number_input(
            "USL",
            format="%.4f",
            key=bu_k,
            on_change=_sync_draft_spec,
            args=(pk, "usl", bu_k),
        )

  st.sidebar.header("3️⃣ 全局样本屏蔽")
  active_ref_lsl = float(specs_map[focus_key]["lsl"])
  active_ref_usl = float(specs_map[focus_key]["usl"])

  spike_mode = st.sidebar.selectbox(
      "单点极端尖峰屏蔽（传感器/编码器 Bug）",
      options=[
          "智能抗差识别（偏离中位数 N 倍 MAD）",
          "按各项目 SPEC 公差倍数识别",
          "自定义单点有效数值区间",
          "不启用单点屏蔽",
      ],
      index=0,
      key=f"v1_spike_mode_{dataset_key}",
  )

  spike_param_val = 15.0
  pt_min_val, pt_max_val = None, None
  if spike_mode == "智能抗差识别（偏离中位数 N 倍 MAD）":
    sp_c1, sp_c2 = st.sidebar.columns([1.15, 1.35])
    spike_param_val = sp_c1.number_input(
        "MAD 阈值倍数",
        min_value=3.0,
        max_value=200.0,
        value=15.0,
        step=1.0,
        key=f"v1_mad_mult_{dataset_key}",
    )
    spike_action = sp_c2.selectbox(
        "异常点处理方式",
        options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
        index=0,
        key=f"v1_sp_act_mad_{dataset_key}",
    )
  elif spike_mode == "按各项目 SPEC 公差倍数识别":
    sp_c1, sp_c2 = st.sidebar.columns([1.15, 1.35])
    spike_param_val = sp_c1.number_input(
        "公差跨度倍数",
        min_value=1.0,
        max_value=50.0,
        value=3.0,
        step=0.5,
        key=f"v1_tol_mult_{dataset_key}",
    )
    spike_action = sp_c2.selectbox(
        "异常点处理方式",
        options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
        index=0,
        key=f"v1_sp_act_tol_{dataset_key}",
    )
  elif spike_mode == "自定义单点有效数值区间":
    sp_c1, sp_c2 = st.sidebar.columns(2)
    pt_min_val = sp_c1.number_input(
        "单点最小值",
        value=float(active_ref_lsl - (active_ref_usl - active_ref_lsl)),
        format="%.4f",
        key=f"v1_pt_min_{dataset_key}",
    )
    pt_max_val = sp_c2.number_input(
        "单点最大值",
        value=float(active_ref_usl + (active_ref_usl - active_ref_lsl)),
        format="%.4f",
        key=f"v1_pt_max_{dataset_key}",
    )
    spike_action = sp_c2.selectbox(
        "异常点处理方式",
        options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
        index=0,
        key=f"v1_sp_act_rng_{dataset_key}",
    )
  else:
    spike_action = "置空该单元格（保留行内其他列）"

  exclude_ranges_str = st.sidebar.text_input(
      "屏蔽行号区间（支持多段）",
      value="",
      placeholder="例如: 1-250, 600-630",
      key=f"v1_excl_rows_{dataset_key}",
  )

  filter_mode = st.sidebar.selectbox(
      "行均值数值筛选规则",
      options=[
          "不屏蔽（保留全部行）",
          "按各项目 SPEC 范围过滤",
          "按自定义范围过滤（超出设定区间屏蔽）",
      ],
      index=1,
      key=f"v1_filter_mode_{dataset_key}",
  )

  custom_min, custom_max = None, None
  if filter_mode == "按自定义范围过滤（超出设定区间屏蔽）":
    c_min, c_max = st.sidebar.columns(2)
    custom_min = c_min.number_input(
        "允许最小值",
        value=float(active_ref_lsl),
        format="%.4f",
        key=f"v1_c_min_{dataset_key}",
    )
    custom_max = c_max.number_input(
        "允许最大值",
        value=float(active_ref_usl),
        format="%.4f",
        key=f"v1_c_max_{dataset_key}",
    )
    if custom_min >= custom_max:
      st.sidebar.error("⚠️ 最小值必须小于最大值！")
      st.stop()

  st.sidebar.markdown("---")
  with st.sidebar.expander("⚙️ 西格玛 / CPK 波动校准", expanded=False):
    sigma_target_proj = st.selectbox(
        "校准作用项目",
        options=["当前聚焦项目"] + confirmed_projects,
        index=0,
        key=f"v1_sig_proj_{dataset_key}",
    )
    enable_sigma_tuning = st.checkbox(
        "启用西格玛美化校准（全图与导出表同步）",
        value=False,
        key=f"v1_en_sig_{dataset_key}",
    )
    tuning_mode = st.radio(
        "校准方式",
        options=["直接指定目标西格玛 (σ)", "按目标 CPK 自动推算西格玛"],
        index=0,
        key=f"v1_tun_mode_{dataset_key}",
    )
    center_align_pct = st.slider(
        "均值向 Target 居中比例 (%)",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
        key=f"v1_ctr_pct_{dataset_key}",
    )
    if tuning_mode == "直接指定目标西格玛 (σ)":
      manual_target_sigma = st.number_input(
          "目标组内西格玛 (Target Within σ)",
          min_value=0.000001,
          value=0.020000,
          format="%.6f",
          key=f"v1_man_sig_{dataset_key}",
      )
      target_cpk_goal = 1.33
    else:
      manual_target_sigma = None
      target_cpk_goal = st.selectbox(
          "目标 CPK 标准",
          options=[1.33, 1.50, 1.67, 2.00],
          index=0,
          key=f"v1_tgt_cpk_{dataset_key}",
      )

  project_bundles = {}
  for p_name in confirmed_projects:
    pk = f"{dataset_key}::{p_name}"
    sp = specs_map[pk]
    if sp["lsl"] >= sp["usl"]:
      continue
    apply_tun_p = enable_sigma_tuning and (
        sigma_target_proj == "当前聚焦项目" and p_name == current_focus_proj
        or sigma_target_proj == p_name
    )
    b_data = cached_build_v1_bundle(
        df_raw,
        tuple(proj_map[p_name]),
        sp["lsl"],
        sp["target"],
        sp["usl"],
        spike_mode,
        float(spike_param_val),
        spike_action,
        pt_min_val,
        pt_max_val,
        exclude_ranges_str,
        filter_mode,
        custom_min,
        custom_max,
        apply_tun_p,
        int(center_align_pct),
        tuning_mode,
        manual_target_sigma,
        float(target_cpk_goal),
    )
    if b_data is not None:
      b_data["fp"] = _bundle_fingerprint(b_data)
      project_bundles[p_name] = b_data

  if not project_bundles:
    st.error(
        "当前筛选条件下，所选项目有效数据点不足 2 个或 SPEC 范围无效，请调整后点击「生成 / 更新所选项目图表」。"
    )
    st.stop()

  ready_projects = list(project_bundles.keys())
  render_v1_header(stacked_banner)

  def default_titles_for_project(p_name):
    return (
        f"{p_name} — Process Capability Report",
        f"{p_name} — Box Plot",
        f"{p_name} — Time Series Plot",
        f"{p_name} — Scatter Series Plot",
        f"{p_name}均值",
    )

  def ensure_project_title_keys(p_name):
    d_cap, d_box, d_ts, d_sc, d_mean = default_titles_for_project(p_name)
    k_cap = f"v1_t_cap_{dataset_key}_{p_name}"
    k_box = f"v1_t_box_{dataset_key}_{p_name}"
    k_ts = f"v1_t_ts_{dataset_key}_{p_name}"
    k_sc = f"v1_t_sc_{dataset_key}_{p_name}"
    k_mean = f"v1_t_mean_{dataset_key}_{p_name}"
    st.session_state.setdefault(k_cap, d_cap)
    st.session_state.setdefault(k_box, d_box)
    st.session_state.setdefault(k_ts, d_ts)
    st.session_state.setdefault(k_sc, d_sc)
    st.session_state.setdefault(k_mean, d_mean)
    return k_cap, k_box, k_ts, k_sc, k_mean

  top_bar1, top_bar2 = st.columns([3.5, 1.2])
  with top_bar1:
    with st.expander(
        "✏️ 自定义各项目图表主标题（默认保留标准后缀，特殊情况可直接删改）",
        expanded=False,
    ):
      title_target_proj = st.selectbox(
          "选择要自定义标题的项目",
          options=ready_projects,
          key=f"v1_title_proj_sel_{dataset_key}",
      )
      k_cap, k_box, k_ts, k_sc, k_mean = ensure_project_title_keys(
          title_target_proj
      )
      t_c1, t_c2 = st.columns(2)
      t_c1.text_input("能力报告标题", key=k_cap)
      t_c2.text_input("箱线图标题", key=k_box)
      t_c3, t_c4 = st.columns(2)
      t_c3.text_input("时间序列图标题", key=k_ts)
      t_c4.text_input("散点序列图标题", key=k_sc)
      st.text_input("单行均值图标题", key=k_mean)

      if st.button(
          f"↩️ 恢复 [{title_target_proj}] 默认标准后缀标题",
          key=f"v1_reset_titles_{dataset_key}_{title_target_proj}",
      ):
        d_cap, d_box, d_ts, d_sc, d_mean = default_titles_for_project(
            title_target_proj
        )
        st.session_state[k_cap] = d_cap
        st.session_state[k_box] = d_box
        st.session_state[k_ts] = d_ts
        st.session_state[k_sc] = d_sc
        st.session_state[k_mean] = d_mean
        st.rerun()

  with top_bar2:
    show_outer_border = st.checkbox(
        "🖼️ 图像浅灰外边框",
        value=True,
        key=f"v1_show_border_{dataset_key}",
    )

  def get_project_titles(p_name):
    d_cap, d_box, d_ts, d_sc, d_mean = default_titles_for_project(p_name)
    k_cap, k_box, k_ts, k_sc, k_mean = ensure_project_title_keys(p_name)
    v_cap = str(st.session_state.get(k_cap, "")).strip()
    v_box = str(st.session_state.get(k_box, "")).strip()
    v_ts = str(st.session_state.get(k_ts, "")).strip()
    v_sc = str(st.session_state.get(k_sc, "")).strip()
    v_mean = str(st.session_state.get(k_mean, "")).strip()
    return (
        v_cap if v_cap else d_cap,
        v_box if v_box else d_box,
        v_ts if v_ts else d_ts,
        v_sc if v_sc else d_sc,
        v_mean if v_mean else d_mean,
    )

  ASPECT_OPTIONS = [
      "4 : 3（PPT 多图/四宫格）",
      "3 : 2（紧凑双图对比）",
      "16 : 9（宽屏展示）",
      "2.2 : 1（超宽横幅）",
      "自定义比例",
  ]

  def render_aspect_selector(container_col, key_prefix, default_idx=0):
    preset = container_col.selectbox(
        "图像比例",
        options=ASPECT_OPTIONS,
        index=default_idx,
        key=f"v1_{key_prefix}_{dataset_key}_aspect_preset",
    )
    if preset == "4 : 3（PPT 多图/四宫格）":
      fw, fh = 9.6, 7.2
    elif preset == "3 : 2（紧凑双图对比）":
      fw, fh = 10.5, 7.0
    elif preset == "16 : 9（宽屏展示）":
      fw, fh = 12.8, 7.2
    elif preset == "2.2 : 1（超宽横幅）":
      fw, fh = 13.6, 6.2
    else:
      sub_c1, sub_c2 = container_col.columns(2)
      rw = sub_c1.number_input(
          "宽比",
          min_value=1.0,
          max_value=30.0,
          value=4.0,
          step=0.5,
          key=f"v1_{key_prefix}_{dataset_key}_rw",
      )
      rh = sub_c2.number_input(
          "高比",
          min_value=1.0,
          max_value=30.0,
          value=3.0,
          step=0.5,
          key=f"v1_{key_prefix}_{dataset_key}_rh",
      )
      fh = 7.0
      fw = float(np.clip(fh * (rw / rh), 6.5, 16.0))

    px_w = int(min(1150, max(620, fw * 85)))
    return fw, fh, px_w

  summary_rows = []
  for p_name in ready_projects:
    b = project_bundles[p_name]
    summary_rows.append({
        "项目组": p_name,
        "通道数": len(b["cols"]),
        "有效行数": len(b["df_clean"]),
        "总样本 N": b["total_n"],
        "屏蔽异常单点": b["masked_cells"],
        "LSL": b["lsl"],
        "Target": b["target"],
        "USL": b["usl"],
        "均值": round(b["sample_mean"], 4),
        "组内σ": round(b["std_within"], 5),
        "CPK": round(b["cpk"], 2),
        "PPK": round(b["ppk"], 2),
    })
  st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

  if len(ready_projects) > 1:
    zip_state_key = f"v1_zip_bytes_{dataset_key}"
    zip_sig_key = f"v1_zip_sig_{dataset_key}"
    cur_zip_sig = (
        "|".join(f"{pn}:{project_bundles[pn]['fp']}" for pn in ready_projects)
        + f"|border={show_outer_border}"
    )
    if st.button(
        "📦 打包生成多项目 SPC 图表 ZIP",
        key=f"v1_prep_zip_{dataset_key}",
    ):
      zip_buf = io.BytesIO()
      with zipfile.ZipFile(
          zip_buf, "w", compression=zipfile.ZIP_DEFLATED
      ) as zf:
        for p_name in ready_projects:
          b = project_bundles[p_name]
          t_cap, t_box, t_ts, t_sc, t_mean = get_project_titles(p_name)
          safe_p = re.sub(r'[\\/*?:"<>|]', "_", p_name)
          zf.writestr(
              f"{safe_p}/{safe_p}_CPK.png",
              render_capability_from_bundle(
                  b, t_cap, 9.6, 7.2, show_outer_border
              ),
          )
          zf.writestr(
              f"{safe_p}/{safe_p}_BoxPlot.png",
              render_box_from_bundle(
                  b,
                  t_box,
                  9.6,
                  7.2,
                  False,
                  False,
                  False,
                  4,
                  show_outer_border,
              ),
          )
          zf.writestr(
              f"{safe_p}/{safe_p}_TimeSeries.png",
              render_time_series_from_bundle(
                  b,
                  t_ts,
                  13.6,
                  6.2,
                  "连续重排序号 (1..N，无断层)",
                  "自动缩放 (Auto)",
                  None,
                  None,
                  show_outer_border,
                  max_pts=8000,
              ),
          )
          zf.writestr(
              f"{safe_p}/{safe_p}_ScatterSeries.png",
              render_scatter_from_bundle(
                  b,
                  t_sc,
                  13.6,
                  6.2,
                  "连续重排序号 (1..N，无断层)",
                  "自动缩放 (Auto)",
                  None,
                  None,
                  None,
                  show_outer_border,
                  max_pts=8000,
              ),
          )
          zf.writestr(
              f"{safe_p}/{safe_p}_RowMean_Trend.png",
              render_row_mean_from_bundle(
                  b,
                  t_mean,
                  13.6,
                  6.2,
                  "连续重排序号 (1..N，无断层)",
                  "自动缩放 (Auto)",
                  None,
                  None,
                  show_outer_border,
                  max_pts=8000,
              ),
          )
      st.session_state[zip_state_key] = zip_buf.getvalue()
      st.session_state[zip_sig_key] = cur_zip_sig

    if (
        st.session_state.get(zip_state_key)
        and st.session_state.get(zip_sig_key) == cur_zip_sig
    ):
      safe_sheet = re.sub(r'[\\/*?:"<>|]', "_", selected_sheet)
      st.download_button(
          "下载 ZIP 包",
          data=st.session_state[zip_state_key],
          file_name=f"{safe_sheet}_多项目SPC图表包.zip",
          mime="application/zip",
          key=f"v1_dl_zip_{dataset_key}",
      )

  proj_tabs = st.tabs([f"📊 {p_name}" for p_name in ready_projects])
  for p_tab, p_name in zip(proj_tabs, ready_projects):
    with p_tab:
      b = project_bundles[p_name]
      t_cap, t_box, t_ts, t_sc, t_mean = get_project_titles(p_name)
      safe_prefix = re.sub(r'[\\/*?:"<>|]', "_", p_name)
      d_ymin, d_ymax = b["val_min"], b["val_max"]
      p_lsl, p_usl = b["lsl"], b["usl"]

      tab_cap, tab_box, tab_ts, tab_sc, tab_mean, tab_data = st.tabs([
          "1️⃣ 过程能力报告 (CPK)",
          "2️⃣ 分组箱线图 (Box Plot)",
          "3️⃣ 多通道时间序列图 (Time Series)",
          "4️⃣ 多通道散点序列图 (Scatter Series)",
          "5️⃣ 单行均值趋势图 (Excel 风格)",
          "6️⃣ 清洗后数据明细与导出",
      ])

      with tab_cap:
        cc1, _ = st.columns([1.8, 3.2])
        cap_w, cap_h, cap_px = render_aspect_selector(
            cc1, f"cap_{p_name}", default_idx=0
        )
        png_cap = render_capability_from_bundle(
            b, t_cap, cap_w, cap_h, show_outer_border
        )
        st.image(png_cap, width=cap_px)
        render_chart_action_bar(
            png_cap, f"{safe_prefix}_CPK.png", f"v1_cap_{dataset_key}_{p_name}"
        )

      with tab_box:
        bc1, bc2, bc3, bc4, bc5 = st.columns([1.2, 1.2, 1.3, 0.9, 1.6])
        show_box_median = bc1.checkbox(
            "显示中位数 (Median)",
            value=False,
            key=f"v1_bmed_{dataset_key}_{p_name}",
        )
        show_box_mean = bc2.checkbox(
            "显示均值 (Mean)",
            value=False,
            key=f"v1_bmean_{dataset_key}_{p_name}",
        )
        show_box_outliers = bc3.checkbox(
            "显示异常点 (Outliers)",
            value=False,
            key=f"v1_bout_{dataset_key}_{p_name}",
        )
        box_decimals = bc4.selectbox(
            "小数位",
            options=[2, 3, 4, 5, 6],
            index=2,
            key=f"v1_bdec_{dataset_key}_{p_name}",
        )
        box_w, box_h, box_px = render_aspect_selector(
            bc5, f"box_{p_name}", default_idx=0
        )

        png_box = render_box_from_bundle(
            b,
            t_box,
            box_w,
            box_h,
            show_box_outliers,
            show_box_median,
            show_box_mean,
            box_decimals,
            show_outer_border,
        )
        st.image(png_box, width=box_px)
        render_chart_action_bar(
            png_box,
            f"{safe_prefix}_BoxPlot.png",
            f"v1_box_{dataset_key}_{p_name}",
        )

      with tab_ts:
        tc1, tc2, tc3, tc4, tc5 = st.columns([1.6, 1.4, 0.9, 0.9, 1.5])
        ts_x_mode = tc1.selectbox(
            "X轴序号",
            options=["连续重排序号 (1..N，无断层)", "保留原始表格行号 (Row Index)"],
            index=0,
            key=f"v1_ts_x_{dataset_key}_{p_name}",
        )
        ts_y_mode = tc2.selectbox(
            "Y轴尺度",
            options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
            index=0,
            key=f"v1_ts_y_{dataset_key}_{p_name}",
        )
        pad = max((d_ymax - d_ymin) * 0.1, 0.02)
        ts_ymin, ts_ymax = None, None
        if ts_y_mode == "自定义范围 (Manual)":
          ts_ymin = tc3.number_input(
              "Y-Min",
              value=round(d_ymin - pad, 4),
              format="%.4f",
              key=f"v1_ts_ymin_{dataset_key}_{p_name}",
          )
          ts_ymax = tc4.number_input(
              "Y-Max",
              value=round(d_ymax + pad, 4),
              format="%.4f",
              key=f"v1_ts_ymax_{dataset_key}_{p_name}",
          )
        ts_w, ts_h, ts_px = render_aspect_selector(
            tc5, f"ts_{p_name}", default_idx=3
        )

        png_ts = render_time_series_from_bundle(
            b,
            t_ts,
            ts_w,
            ts_h,
            ts_x_mode,
            ts_y_mode,
            ts_ymin,
            ts_ymax,
            show_outer_border,
        )
        st.image(png_ts, width=ts_px)
        render_chart_action_bar(
            png_ts,
            f"{safe_prefix}_TimeSeries.png",
            f"v1_ts_{dataset_key}_{p_name}",
        )

      with tab_sc:
        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(
            [1.5, 1.3, 0.85, 0.85, 0.9, 1.4]
        )
        sc_x_mode = sc1.selectbox(
            "X轴序号",
            options=["连续重排序号 (1..N，无断层)", "保留原始表格行号 (Row Index)"],
            index=0,
            key=f"v1_sc_x_{dataset_key}_{p_name}",
        )
        sc_y_mode = sc2.selectbox(
            "Y轴尺度",
            options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
            index=0,
            key=f"v1_sc_y_{dataset_key}_{p_name}",
        )
        pad = max((d_ymax - d_ymin) * 0.1, 0.02)
        sc_ymin, sc_ymax = None, None
        if sc_y_mode == "自定义范围 (Manual)":
          sc_ymin = sc3.number_input(
              "Y-Min",
              value=round(d_ymin - pad, 4),
              format="%.4f",
              key=f"v1_sc_ymin_{dataset_key}_{p_name}",
          )
          sc_ymax = sc4.number_input(
              "Y-Max",
              value=round(d_ymax + pad, 4),
              format="%.4f",
              key=f"v1_sc_ymax_{dataset_key}_{p_name}",
          )
        sc_pt_size = sc5.number_input(
            "点大小",
            min_value=1.0,
            max_value=40.0,
            value=6.0 if b["total_n"] > 3000 else 10.0,
            step=1.0,
            key=f"v1_sc_pt_{dataset_key}_{p_name}",
        )
        sc_w, sc_h, sc_px = render_aspect_selector(
            sc6, f"sc_{p_name}", default_idx=3
        )

        png_sc = render_scatter_from_bundle(
            b,
            t_sc,
            sc_w,
            sc_h,
            sc_x_mode,
            sc_y_mode,
            sc_ymin,
            sc_ymax,
            sc_pt_size,
            show_outer_border,
        )
        st.image(png_sc, width=sc_px)
        render_chart_action_bar(
            png_sc,
            f"{safe_prefix}_ScatterSeries.png",
            f"v1_sc_{dataset_key}_{p_name}",
        )

      with tab_mean:
        mc1, mc2, mc3, mc4, mc5 = st.columns([1.6, 1.4, 0.9, 0.9, 1.5])
        mean_x_mode = mc1.selectbox(
            "X轴序号",
            options=["连续重排序号 (1..N，无断层)", "保留原始表格行号 (Row Index)"],
            index=0,
            key=f"v1_mean_x_{dataset_key}_{p_name}",
        )
        mean_y_mode = mc2.selectbox(
            "Y轴尺度",
            options=["自动缩放 (Auto)", "自定义范围 (Manual)"],
            index=0,
            key=f"v1_mean_y_{dataset_key}_{p_name}",
        )
        mean_ymin, mean_ymax = None, None
        if mean_y_mode == "自定义范围 (Manual)":
          spec_span = p_usl - p_lsl
          mean_ymin = mc3.number_input(
              "Y-Min",
              value=round(p_lsl - 0.5 * spec_span, 4),
              format="%.4f",
              key=f"v1_mean_ymin_{dataset_key}_{p_name}",
          )
          mean_ymax = mc4.number_input(
              "Y-Max",
              value=round(p_usl + 0.25 * spec_span, 4),
              format="%.4f",
              key=f"v1_mean_ymax_{dataset_key}_{p_name}",
          )
        mean_w, mean_h, mean_px = render_aspect_selector(
            mc5, f"mean_{p_name}", default_idx=3
        )

        png_mean = render_row_mean_from_bundle(
            b,
            t_mean,
            mean_w,
            mean_h,
            mean_x_mode,
            mean_y_mode,
            mean_ymin,
            mean_ymax,
            show_outer_border,
        )
        st.image(png_mean, width=mean_px)
        render_chart_action_bar(
            png_mean,
            f"{safe_prefix}_RowMean_Trend.png",
            f"v1_mean_{dataset_key}_{p_name}",
        )

      with tab_data:
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
          b["df_clean"].to_excel(writer, sheet_name="Valid_Data", index=False)
          b["df_removed"].to_excel(
              writer, sheet_name="Filtered_Out_Rows", index=False
          )
        excel_buf.seek(0)
        st.download_button(
            "下载完整 Excel",
            data=excel_buf,
            file_name=f"{safe_prefix}_Filtered.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"v1_dl_xlsx_{dataset_key}_{p_name}",
        )
        show_all_rows = st.checkbox(
            f"显示全部 {len(b['df_clean'])} 行（默认仅预览前 500 行以节省内存）",
            value=False,
            key=f"v1_show_all_rows_{dataset_key}_{p_name}",
        )
        sub_t1, sub_t2 = st.tabs(
            ["有效数据 (Valid)", "被屏蔽异常行 (Filtered Out)"]
        )
        with sub_t1:
          st.dataframe(
              b["df_clean"] if show_all_rows else b["df_clean"].head(500),
              width="stretch",
          )
        with sub_t2:
          st.dataframe(
              b["df_removed"] if show_all_rows else b["df_removed"].head(500),
              width="stretch",
          )


# ==============================================================================
#                               版本 2.0：多批次对比分析
# ==============================================================================
def run_v2_app():
  render_sidebar_mode_switcher("v2")

  def render_v2_header(compact=False):
    st.markdown(
        """
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px;">
              <span style="background:#2563EB;color:#FFFFFF;font-size:12px;font-weight:700;
                           padding:3px 10px;border-radius:999px;letter-spacing:0.5px;">
                v2.0 · 多批次对比版
              </span>
              <span style="font-size:12px;color:#64748B;">
                共享项目与 SPEC 设定 · 自定义样本区间 · 多批次含组直方图与汇报对比
              </span>
            </div>
            """,
        unsafe_allow_html=True,
    )
    st.title("在线检测 SPC 与过程能力分析系统")
    st.caption("Created by xu  |  版本 2.0（多批次联合分析与对比）")
    if not compact:
      st.markdown(
          """
                <div style="border-left:4px solid #2563EB;background:rgba(37,99,235,0.06);
                            padding:10px 14px;border-radius:0 8px 8px 0;margin:8px 0 14px 0;font-size:13px;">
                  <strong>2.0 多批次工作流：</strong>
                  1) 在左侧上传 <strong>2–3 个同表头批次文件</strong>；
                  2) 统一配置<strong>待生成项目</strong>、<strong>SPEC</strong> 与<strong>自定义样本区间</strong>；
                  3) 查看<strong>多批次含组直方图（可加拟合线）</strong>与<strong>CPK 对比</strong>，快速挑出最适合汇报的批次。
                </div>
                """,
          unsafe_allow_html=True,
      )

  @st.cache_data(show_spinner=False, max_entries=8)
  def prepare_clean_raw_df(raw_sheet_df):
    df_w = raw_sheet_df.dropna(how="all").reset_index(drop=True).copy()
    if df_w.empty:
      return None, []
    df_w.insert(0, "Row_Index", np.arange(1, len(df_w) + 1, dtype=np.int32))
    num_cols = []
    for col in df_w.columns:
      if col == "Row_Index":
        continue
      converted = pd.to_numeric(df_w[col], errors="coerce")
      non_null = df_w[col].notna().sum()
      if non_null > 0 and converted.notna().sum() / non_null >= 0.3:
        df_w[col] = converted.astype(np.float32)
        num_cols.append(col)
    return df_w, num_cols

  st.sidebar.header("1️⃣ 多批次数据源（2-3个批次）")
  uploaded_files = st.sidebar.file_uploader(
      "上传 2–3 个批次检测数据表 (.xlsx / .csv)",
      type=["xlsx", "xls", "csv"],
      accept_multiple_files=True,
      key="v2_uploader",
  )

  if not uploaded_files or len(uploaded_files) < 2:
    render_v2_header(compact=False)
    if not uploaded_files:
      st.info(
          "👈 请在左侧边栏上传 **2–3 个批次**的检测数据表格（建议表头相同，便于共用项目与 SPEC 设定）。"
      )
    else:
      st.warning(
          f"当前仅上传了 1 个文件（{uploaded_files[0].name}）。2.0 多批次对比版建议同时上传 **2–3 个批次文件**进行对比；请继续添加批次文件。"
      )
    st.stop()

  batch_entries = []
  for f_idx, up_file in enumerate(uploaded_files):
    try:
      s_dict = load_workbook_sheets(up_file.getvalue(), up_file.name)
    except Exception as exc:
      st.error(f"❌ 批次文件 [{up_file.name}] 读取失败：{exc}")
      st.stop()
    sheet_names = list(s_dict.keys())
    chosen_sheet = st.sidebar.selectbox(
        f"批次 {f_idx + 1} 工作表 ({up_file.name})",
        options=sheet_names,
        index=0,
        key=f"v2_sheet_{f_idx}_{up_file.name}",
    )
    df_clean_raw, num_cols = prepare_clean_raw_df(s_dict[chosen_sheet])
    if df_clean_raw is None or not num_cols:
      st.error(
          f"❌ 批次 [{up_file.name} - {chosen_sheet}] 未识别到有效数值检测列。"
      )
      st.stop()

    batch_label = f"批次{f_idx + 1}: {os.path.splitext(up_file.name)[0]}"
    if any(b["label"] == batch_label for b in batch_entries):
      batch_label = f"{batch_label} (#{f_idx + 1})"

    batch_entries.append({
        "idx": f_idx,
        "file_name": up_file.name,
        "sheet": chosen_sheet,
        "label": batch_label,
        "df_raw": df_clean_raw,
        "numeric_cols": num_cols,
        "spec_info": detect_spec_from_columns(
            df_clean_raw, df_clean_raw.columns
        ),
    })

  common_numeric_cols = [
      c
      for c in batch_entries[0]["numeric_cols"]
      if all(c in b["numeric_cols"] for b in batch_entries[1:])
  ]
  union_numeric_cols = []
  for b in batch_entries:
    for c in b["numeric_cols"]:
      if c not in union_numeric_cols:
        union_numeric_cols.append(c)

  shared_pool_cols = (
      common_numeric_cols if common_numeric_cols else union_numeric_cols
  )
  if not common_numeric_cols:
    st.sidebar.warning(
        "⚠️ 各批次数值表头不完全一致，已自动取并集列，请核对各项目通道列。"
    )

  merged_spec_info = {
      "lsl": None,
      "target": None,
      "usl": None,
      "spec_cols": set(),
  }
  for b in batch_entries:
    for k_sp in ("lsl", "target", "usl"):
      if merged_spec_info[k_sp] is None and b["spec_info"][k_sp] is not None:
        merged_spec_info[k_sp] = b["spec_info"][k_sp]
    merged_spec_info["spec_cols"].update(b["spec_info"]["spec_cols"])

  measurement_candidates = [
      c for c in shared_pool_cols if c not in merged_spec_info["spec_cols"]
  ]
  if not measurement_candidates:
    measurement_candidates = shared_pool_cols

  group_order, inferred_groups = infer_parameter_groups(measurement_candidates)
  suggested_default_groups = [
      g for g in group_order if not is_likely_non_measurement(g)
  ]

  dataset_key = "||".join(
      f"{b['file_name']}::{b['sheet']}" for b in batch_entries
  )

  if st.session_state.get("v2_active_dataset_key") != dataset_key:
    st.session_state["v2_active_dataset_key"] = dataset_key
    st.session_state["v2_project_groups_map"] = {
        k: list(v) for k, v in inferred_groups.items()
    }
    st.session_state["v2_draft_projects"] = list(suggested_default_groups)
    st.session_state["v2_confirmed_projects"] = list(suggested_default_groups)
    st.session_state["v2_confirmed_groups_snapshot"] = {
        k: list(v) for k, v in inferred_groups.items()
    }
    st.session_state["v2_selection_dirty"] = False
    st.session_state["v2_project_specs_map"] = {}
    st.session_state["v2_draft_specs_map"] = {}
    st.session_state["v2_spec_dirty"] = False

  proj_map = st.session_state.setdefault(
      "v2_project_groups_map", {k: list(v) for k, v in inferred_groups.items()}
  )
  available_proj_names = list(proj_map.keys())

  draft_default = [
      p
      for p in st.session_state.get(
          "v2_draft_projects", suggested_default_groups
      )
      if p in available_proj_names
  ]

  selected_projects = st.sidebar.multiselect(
      "共用待生成项目 / 参数组",
      options=available_proj_names,
      default=draft_default,
      key=f"v2_ms_draft_projects_{dataset_key}",
  )
  st.session_state["v2_draft_projects"] = selected_projects

  cols_changed_in_expander = False
  with st.sidebar.expander("🔧 调整各项目共用的通道列", expanded=False):
    for p_name in available_proj_names:
      updated_cols = st.multiselect(
          f"[{p_name}] 通道列",
          options=shared_pool_cols,
          default=[c for c in proj_map[p_name] if c in shared_pool_cols],
          key=f"v2_cols_for_{dataset_key}_{p_name}",
      )
      if updated_cols and updated_cols != proj_map[p_name]:
        proj_map[p_name] = updated_cols
        cols_changed_in_expander = True

    new_grp_name = st.text_input(
        "新增共用项目组名称",
        value="",
        placeholder="例如: 涂宽+白边对比",
        key=f"v2_new_grp_name_{dataset_key}",
    )
    new_grp_cols = st.multiselect(
        "选择新增项目组通道列",
        options=shared_pool_cols,
        default=[],
        key=f"v2_new_grp_cols_{dataset_key}",
    )
    if st.button(
        "➕ 添加共用项目组",
        key=f"v2_btn_add_grp_{dataset_key}",
        use_container_width=True,
    ):
      if new_grp_name.strip() and new_grp_cols:
        g_clean = new_grp_name.strip()
        proj_map[g_clean] = list(new_grp_cols)
        if g_clean not in st.session_state["v2_draft_projects"]:
          st.session_state["v2_draft_projects"].append(g_clean)
        st.session_state["v2_selection_dirty"] = True
        st.rerun()

  prev_confirmed = st.session_state.get("v2_confirmed_projects", [])
  prev_snapshot = st.session_state.get("v2_confirmed_groups_snapshot", {})
  current_selected_non_empty = [
      p for p in selected_projects if len(proj_map.get(p, [])) > 0
  ]
  current_snapshot = {
      p: list(proj_map.get(p, [])) for p in current_selected_non_empty
  }

  if (
      current_selected_non_empty != prev_confirmed
      or current_snapshot != prev_snapshot
      or cols_changed_in_expander
  ):
    st.session_state["v2_selection_dirty"] = True

  def compute_recommended_spec_multi(b_list, cols_sel, s_info):
    all_pieces = []
    for b in b_list:
      valid_cols = [c for c in cols_sel if c in b["df_raw"].columns]
      if valid_cols:
        arr = b["df_raw"][valid_cols].to_numpy(dtype=np.float32)
        vv = arr[~np.isnan(arr)]
        if len(vv) > 0:
          all_pieces.append(vv)

    if all_pieces:
      valid_v = np.concatenate(all_pieces)
      mid = float(np.median(valid_v))
      mad = float(np.median(np.abs(valid_v - mid)))
      robust_std = mad * 1.4826 if mad > 0 else float(np.std(valid_v, ddof=1))
      half_tol = max(round(robust_std * 4.5, 4), 0.2) if robust_std > 0 else 1.0
    else:
      mid, half_tol = 0.0, 1.0

    rec_lsl = (
        s_info["lsl"] if s_info["lsl"] is not None else round(mid - half_tol, 4)
    )
    rec_usl = (
        s_info["usl"] if s_info["usl"] is not None else round(mid + half_tol, 4)
    )
    if s_info["target"] is not None:
      rec_target = s_info["target"]
    elif s_info["lsl"] is not None and s_info["usl"] is not None:
      rec_target = round((s_info["lsl"] + s_info["usl"]) / 2.0, 4)
    else:
      rec_target = round(mid, 4)
    return float(rec_lsl), float(rec_target), float(rec_usl)

  specs_map = st.session_state.setdefault("v2_project_specs_map", {})
  draft_specs_map = st.session_state.setdefault("v2_draft_specs_map", {})

  for p_name in current_selected_non_empty:
    p_key = f"{dataset_key}::{p_name}"
    if p_key not in specs_map:
      rl, rt, ru = compute_recommended_spec_multi(
          batch_entries, proj_map[p_name], merged_spec_info
      )
      specs_map[p_key] = {"lsl": rl, "target": rt, "usl": ru}
    if p_key not in draft_specs_map:
      draft_specs_map[p_key] = dict(specs_map[p_key])

  def _sync_v2_draft_spec(p_key, field_name, widget_key):
    draft_specs_map.setdefault(p_key, dict(specs_map.get(p_key, {})))
    draft_specs_map[p_key][field_name] = float(st.session_state[widget_key])
    st.session_state["v2_spec_dirty"] = True

  def _reestimate_v2_spec_callback(
      f_key, l_key, t_key, u_key, b_list_ref, cols_ref, sp_ref
  ):
    rl, rt, ru = compute_recommended_spec_multi(b_list_ref, cols_ref, sp_ref)
    draft_specs_map[f_key] = {"lsl": rl, "target": rt, "usl": ru}
    st.session_state[l_key] = rl
    st.session_state[t_key] = rt
    st.session_state[u_key] = ru
    st.session_state["v2_spec_dirty"] = True

  generate_clicked = st.sidebar.button(
      "🚀 生成 / 更新所选项目图表",
      key=f"v2_btn_gen_charts_{dataset_key}",
      type="primary",
      use_container_width=True,
  )
  if generate_clicked:
    st.session_state["v2_confirmed_projects"] = list(current_selected_non_empty)
    st.session_state["v2_confirmed_groups_snapshot"] = {
        p: list(proj_map.get(p, [])) for p in current_selected_non_empty
    }
    st.session_state["v2_selection_dirty"] = False
    for p_name in current_selected_non_empty:
      p_key = f"{dataset_key}::{p_name}"
      if p_key in draft_specs_map:
        cand = draft_specs_map[p_key]
        if cand.get("lsl", 0.0) < cand.get("usl", 0.0):
          specs_map[p_key] = {
              "lsl": float(cand["lsl"]),
              "target": float(cand["target"]),
              "usl": float(cand["usl"]),
          }
    st.session_state["v2_spec_dirty"] = False

  if st.session_state.get("v2_selection_dirty", False):
    render_v2_header(compact=True)
    if not current_selected_non_empty:
      st.info(
          "👈 当前未选择任何共用项目。请在左侧**「共用待生成项目 / 参数组」**中选择项目，然后点击 **「🚀 生成 / 更新所选项目图表」**。"
      )
    else:
      st.warning(
          f"👈 检测到共用项目或通道列选择已变更（当前已选 {len(current_selected_non_empty)} 个项目：{', '.join(current_selected_non_empty)}）。已暂停自动出图，请点击左侧 **「🚀 生成 / 更新所选项目图表」** 开始生成。"
      )
    st.stop()

  confirmed_projects = [
      p
      for p in st.session_state.get("v2_confirmed_projects", [])
      if p in available_proj_names and len(proj_map.get(p, [])) > 0
  ]

  if not confirmed_projects:
    render_v2_header(compact=True)
    st.info(
        "👈 请在左侧**「共用待生成项目 / 参数组」**中选择至少一个项目，然后点击 **「🚀 生成 / 更新所选项目图表」**。"
    )
    st.stop()

  st.sidebar.header("2️⃣ 共用 SPEC 规格设定")
  st.sidebar.caption("多批次共用同一规格；修改时不实时刷新图表，点上方按钮统一生效")

  current_focus_proj = st.sidebar.selectbox(
      "当前编辑 SPEC 的共用项目",
      options=confirmed_projects,
      index=0,
      key=f"v2_focus_spec_proj_{dataset_key}",
  )
  focus_key = f"{dataset_key}::{current_focus_proj}"
  cur_draft_spec = draft_specs_map.setdefault(
      focus_key, dict(specs_map[focus_key])
  )

  sc1, sc2, sc3 = st.sidebar.columns(3)
  lsl_w_key = f"v2_num_lsl_{focus_key}"
  tgt_w_key = f"v2_num_target_{focus_key}"
  usl_w_key = f"v2_num_usl_{focus_key}"

  st.session_state.setdefault(lsl_w_key, float(cur_draft_spec["lsl"]))
  st.session_state.setdefault(tgt_w_key, float(cur_draft_spec["target"]))
  st.session_state.setdefault(usl_w_key, float(cur_draft_spec["usl"]))

  sc1.number_input(
      "LSL",
      format="%.4f",
      key=lsl_w_key,
      on_change=_sync_v2_draft_spec,
      args=(focus_key, "lsl", lsl_w_key),
  )
  sc2.number_input(
      "Target",
      format="%.4f",
      key=tgt_w_key,
      on_change=_sync_v2_draft_spec,
      args=(focus_key, "target", tgt_w_key),
  )
  sc3.number_input(
      "USL",
      format="%.4f",
      key=usl_w_key,
      on_change=_sync_v2_draft_spec,
      args=(focus_key, "usl", usl_w_key),
  )

  if float(draft_specs_map[focus_key]["lsl"]) >= float(
      draft_specs_map[focus_key]["usl"]
  ):
    st.sidebar.warning(f"⚠️ [{current_focus_proj}] LSL 应小于 USL，生效前请修正。")

  if st.session_state.get("v2_spec_dirty", False):
    st.sidebar.info("SPEC 已修改待生效：请点击上方「🚀 生成 / 更新所选项目图表」")

  st.sidebar.button(
      f"🔄 重新自动估算 [{current_focus_proj}] 共用 SPEC",
      key=f"v2_btn_reest_spec_{focus_key}",
      on_click=_reestimate_v2_spec_callback,
      args=(
          focus_key,
          lsl_w_key,
          tgt_w_key,
          usl_w_key,
          batch_entries,
          proj_map[current_focus_proj],
          merged_spec_info,
      ),
      use_container_width=True,
  )

  if len(confirmed_projects) > 1:
    with st.sidebar.expander("📋 批量查看/修改全部共用项目 SPEC", expanded=False):
      for p_name in confirmed_projects:
        pk = f"{dataset_key}::{p_name}"
        d_sp = draft_specs_map.setdefault(pk, dict(specs_map[pk]))
        st.caption(f"**{p_name}**")
        b1, b2, b3 = st.columns(3)
        bl_k = f"v2_batch_lsl_{pk}"
        bt_k = f"v2_batch_tgt_{pk}"
        bu_k = f"v2_batch_usl_{pk}"
        st.session_state.setdefault(bl_k, float(d_sp["lsl"]))
        st.session_state.setdefault(bt_k, float(d_sp["target"]))
        st.session_state.setdefault(bu_k, float(d_sp["usl"]))
        b1.number_input(
            "LSL",
            format="%.4f",
            key=bl_k,
            on_change=_sync_v2_draft_spec,
            args=(pk, "lsl", bl_k),
        )
        b2.number_input(
            "Target",
            format="%.4f",
            key=bt_k,
            on_change=_sync_v2_draft_spec,
            args=(pk, "target", bt_k),
        )
        b3.number_input(
            "USL",
            format="%.4f",
            key=bu_k,
            on_change=_sync_v2_draft_spec,
            args=(pk, "usl", bu_k),
        )

  st.sidebar.header("3️⃣ 全局样本屏蔽与区间")
  active_ref_lsl = float(specs_map[focus_key]["lsl"])
  active_ref_usl = float(specs_map[focus_key]["usl"])

  spike_mode = st.sidebar.selectbox(
      "单点极端尖峰屏蔽（传感器/编码器 Bug）",
      options=[
          "智能抗差识别（偏离中位数 N 倍 MAD）",
          "按各项目 SPEC 公差倍数识别",
          "自定义单点有效数值区间",
          "不启用单点屏蔽",
      ],
      index=0,
      key=f"v2_spike_mode_{dataset_key}",
  )

  spike_param_val = 15.0
  pt_min_val, pt_max_val = None, None
  if spike_mode == "智能抗差识别（偏离中位数 N 倍 MAD）":
    sp_c1, sp_c2 = st.sidebar.columns([1.15, 1.35])
    spike_param_val = sp_c1.number_input(
        "MAD 阈值倍数",
        min_value=3.0,
        max_value=200.0,
        value=15.0,
        step=1.0,
        key=f"v2_mad_mult_{dataset_key}",
    )
    spike_action = sp_c2.selectbox(
        "异常点处理方式",
        options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
        index=0,
        key=f"v2_sp_act_mad_{dataset_key}",
    )
  elif spike_mode == "按各项目 SPEC 公差倍数识别":
    sp_c1, sp_c2 = st.sidebar.columns([1.15, 1.35])
    spike_param_val = sp_c1.number_input(
        "公差跨度倍数",
        min_value=1.0,
        max_value=50.0,
        value=3.0,
        step=0.5,
        key=f"v2_tol_mult_{dataset_key}",
    )
    spike_action = sp_c2.selectbox(
        "异常点处理方式",
        options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
        index=0,
        key=f"v2_sp_act_tol_{dataset_key}",
    )
  elif spike_mode == "自定义单点有效数值区间":
    sp_c1, sp_c2 = st.sidebar.columns(2)
    pt_min_val = sp_c1.number_input(
        "单点最小值",
        value=float(active_ref_lsl - (active_ref_usl - active_ref_lsl)),
        format="%.4f",
        key=f"v2_pt_min_{dataset_key}",
    )
    pt_max_val = sp_c2.number_input(
        "单点最大值",
        value=float(active_ref_usl + (active_ref_usl - active_ref_lsl)),
        format="%.4f",
        key=f"v2_pt_max_{dataset_key}",
    )
    spike_action = sp_c2.selectbox(
        "异常点处理方式",
        options=["置空该单元格（保留行内其他列）", "剔除包含异常点的整行"],
        index=0,
        key=f"v2_sp_act_rng_{dataset_key}",
    )
  else:
    spike_action = "置空该单元格（保留行内其他列）"

  exclude_ranges_str = st.sidebar.text_input(
      "屏蔽行号区间（支持多段，各批次同步）",
      value="",
      placeholder="例如: 1-250, 600-630",
      key=f"v2_excl_rows_{dataset_key}",
  )

  filter_mode = st.sidebar.selectbox(
      "行均值数值筛选规则",
      options=[
          "不屏蔽（保留全部行）",
          "按各项目 SPEC 范围过滤",
          "按自定义范围过滤（超出设定区间屏蔽）",
      ],
      index=1,
      key=f"v2_filter_mode_{dataset_key}",
  )

  custom_min, custom_max = None, None
  if filter_mode == "按自定义范围过滤（超出设定区间屏蔽）":
    c_min, c_max = st.sidebar.columns(2)
    custom_min = c_min.number_input(
        "允许最小值",
        value=float(active_ref_lsl),
        format="%.4f",
        key=f"v2_c_min_{dataset_key}",
    )
    custom_max = c_max.number_input(
        "允许最大值",
        value=float(active_ref_usl),
        format="%.4f",
        key=f"v2_c_max_{dataset_key}",
    )
    if custom_min >= custom_max:
      st.sidebar.error("⚠️ 最小值必须小于最大值！")
      st.stop()

  sample_range_mode = st.sidebar.selectbox(
      "多批次样本区间对齐（防长短不一）",
      options=[
          "全部有效样本（默认）",
          "对齐最短批次样本数（截断到 Min N）",
          "自定义有效样本序号区间 (Start..End)",
      ],
      index=0,
      key=f"v2_sample_range_mode_{dataset_key}",
  )

  custom_seq_start, custom_seq_end = 1, 500
  if sample_range_mode == "自定义有效样本序号区间 (Start..End)":
    sr1, sr2 = st.sidebar.columns(2)
    custom_seq_start = int(
        sr1.number_input(
            "起始序号",
            min_value=1,
            value=1,
            step=10,
            key=f"v2_seq_start_{dataset_key}",
        )
    )
    custom_seq_end = int(
        sr2.number_input(
            "结束序号",
            min_value=1,
            value=500,
            step=50,
            key=f"v2_seq_end_{dataset_key}",
        )
    )
    if custom_seq_start > custom_seq_end:
      st.sidebar.error("⚠️ 起始序号不能大于结束序号！")
      st.stop()

  st.sidebar.markdown("---")
  with st.sidebar.expander("⚙️ 西格玛 / CPK 波动校准", expanded=False):
    sigma_target_proj = st.selectbox(
        "校准作用项目",
        options=["当前聚焦项目"] + confirmed_projects,
        index=0,
        key=f"v2_sig_proj_{dataset_key}",
    )
    sigma_target_batch = st.selectbox(
        "校准作用批次范围",
        options=["全部对比批次"] + [b["label"] for b in batch_entries],
        index=0,
        key=f"v2_sig_batch_{dataset_key}",
    )
    enable_sigma_tuning = st.checkbox(
        "启用西格玛美化校准（全图与导出表同步）",
        value=False,
        key=f"v2_en_sig_{dataset_key}",
    )
    tuning_mode = st.radio(
        "校准方式",
        options=["直接指定目标西格玛 (σ)", "按目标 CPK 自动推算西格玛"],
        index=0,
        key=f"v2_tun_mode_{dataset_key}",
    )
    center_align_pct = st.slider(
        "均值向 Target 居中比例 (%)",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
        key=f"v2_ctr_pct_{dataset_key}",
    )
    if tuning_mode == "直接指定目标西格玛 (σ)":
      manual_target_sigma = st.number_input(
          "目标组内西格玛 (Target Within σ)",
          min_value=0.000001,
          value=0.020000,
          format="%.6f",
          key=f"v2_man_sig_{dataset_key}",
      )
      target_cpk_goal = 1.33
    else:
      manual_target_sigma = None
      target_cpk_goal = st.selectbox(
          "目标 CPK 标准",
          options=[1.33, 1.50, 1.67, 2.00],
          index=0,
          key=f"v2_tgt_cpk_{dataset_key}",
      )

  bundles_by_project = {}
  for p_name in confirmed_projects:
    pk = f"{dataset_key}::{p_name}"
    sp = specs_map[pk]
    if sp["lsl"] >= sp["usl"]:
      continue

    stage1_map = {}
    for b_entry in batch_entries:
      pre = cached_prefilter_v2_batch(
          b_entry["df_raw"],
          b_entry["label"],
          tuple(proj_map[p_name]),
          sp["lsl"],
          sp["target"],
          sp["usl"],
          spike_mode,
          float(spike_param_val),
          spike_action,
          pt_min_val,
          pt_max_val,
          exclude_ranges_str,
          filter_mode,
          custom_min,
          custom_max,
      )
      if pre is not None:
        stage1_map[b_entry["label"]] = pre

    if not stage1_map:
      continue

    min_valid_len = min(len(v["df_clean"]) for v in stage1_map.values())
    p_batch_map = {}
    for b_lbl, pre in stage1_map.items():
      df_c_sub = pre["df_clean"].copy()
      n_cur = len(df_c_sub)

      if sample_range_mode == "对齐最短批次样本数（截断到 Min N）":
        keep_mask = np.arange(n_cur) < min_valid_len
      elif sample_range_mode == "自定义有效样本序号区间 (Start..End)":
        seq_1based = np.arange(1, n_cur + 1)
        keep_mask = (seq_1based >= custom_seq_start) & (
            seq_1based <= custom_seq_end
        )
      else:
        keep_mask = np.ones(n_cur, dtype=bool)

      df_c_final = df_c_sub[keep_mask].copy().reset_index(drop=True)
      df_r_final = pd.concat(
          [pre["df_removed"], df_c_sub[~keep_mask]], ignore_index=True
      )

      proj_match = (
          sigma_target_proj == "当前聚焦项目" and p_name == current_focus_proj
      ) or (sigma_target_proj == p_name)
      batch_match = (sigma_target_batch == "全部对比批次") or (
          sigma_target_batch == b_lbl
      )
      apply_tun_b = bool(enable_sigma_tuning and proj_match and batch_match)

      b_obj = _compute_spc_metrics_from_clean(
          df_c_final,
          df_r_final,
          pre["masked_cells"],
          pre["valid_cols"],
          sp["lsl"],
          sp["target"],
          sp["usl"],
          apply_tun_b,
          int(center_align_pct),
          tuning_mode,
          manual_target_sigma,
          float(target_cpk_goal),
          extra_meta={"batch_label": b_lbl},
      )
      if b_obj is not None:
        b_obj["fp"] = _bundle_fingerprint(b_obj)
        p_batch_map[b_lbl] = b_obj

    if p_batch_map:
      bundles_by_project[p_name] = p_batch_map

  if not bundles_by_project:
    st.error(
        "当前筛选条件或样本区间下，各批次有效数据点不足 2 个或 SPEC 无效，请调整后重试。"
    )
    st.stop()

  ready_projects = list(bundles_by_project.keys())
  batch_labels_all = tuple(b["label"] for b in batch_entries)
  render_v2_header(compact=True)

  top_bar1, top_bar2 = st.columns([3.5, 1.2])
  with top_bar1:
    with st.expander("✏️ 自定义对比图 / 含组直方图主标题", expanded=False):
      title_proj_sel = st.selectbox(
          "选择项目", options=ready_projects, key=f"v2_t_proj_{dataset_key}"
      )
      k_cmp = f"v2_t_cmp_{dataset_key}_{title_proj_sel}"
      k_hist = f"v2_t_hist_{dataset_key}_{title_proj_sel}"
      k_mean = f"v2_t_mean_{dataset_key}_{title_proj_sel}"
      k_cap = f"v2_t_cap_{dataset_key}_{title_proj_sel}"
      k_box = f"v2_t_box_{dataset_key}_{title_proj_sel}"

      st.session_state.setdefault(
          k_cmp, f"{title_proj_sel} — 多批次过程分布与 CPK 对比"
      )
      st.session_state.setdefault(
          k_hist, f"{title_proj_sel} — 多批次含组直方图"
      )
      st.session_state.setdefault(k_mean, f"{title_proj_sel}均值对比")
      st.session_state.setdefault(
          k_cap, f"{title_proj_sel} — Process Capability Report"
      )
      st.session_state.setdefault(k_box, f"{title_proj_sel} — Box Plot")

      c_t1, c_t2 = st.columns(2)
      c_t1.text_input("多批次分布与 CPK 对比图标题", key=k_cmp)
      c_t2.text_input("多批次含组直方图标题", key=k_hist)
      c_t3, c_t4 = st.columns(2)
      c_t3.text_input("多批次均值趋势图标题", key=k_mean)
      c_t4.text_input("单批次能力报告标题前缀", key=k_cap)
      st.text_input("箱线图标题前缀", key=k_box)

  with top_bar2:
    show_outer_border = st.checkbox(
        "🖼️ 图像浅灰外边框",
        value=True,
        key=f"v2_show_border_{dataset_key}",
    )

  st.subheader("多批次指标横向对比总览")
  st.caption(f"当前样本区间规则：{sample_range_mode}")

  cmp_rows = []
  for p_name in ready_projects:
    for b_lbl in batch_labels_all:
      b = bundles_by_project[p_name].get(b_lbl)
      if b is None:
        continue
      cmp_rows.append({
          "项目组": p_name,
          "批次": b_lbl,
          "有效行数": len(b["df_clean"]),
          "总样本 N": b["total_n"],
          "屏蔽单点": b["masked_cells"],
          "LSL": b["lsl"],
          "Target": b["target"],
          "USL": b["usl"],
          "均值": round(b["sample_mean"], 4),
          "组内σ": round(b["std_within"], 5),
          "CPK": round(b["cpk"], 2),
          "PPK": round(b["ppk"], 2),
          "实测PPM": round(b["obs_total"], 1),
      })

  st.dataframe(pd.DataFrame(cmp_rows), width="stretch", hide_index=True)

  v2_zip_state_key = f"v2_zip_bytes_{dataset_key}"
  v2_zip_sig_key = f"v2_zip_sig_{dataset_key}"
  v2_cur_zip_sig = (
      "|".join(
          f"{pn}:{','.join(bundles_by_project[pn][bl]['fp'] for bl in bundles_by_project[pn])}"
          for pn in ready_projects
      )
      + f"|border={show_outer_border}"
  )
  if st.button(
      "📦 打包生成多批次对比图表 ZIP",
      key=f"v2_prep_zip_{dataset_key}",
  ):
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
      for p_name in ready_projects:
        safe_p = re.sub(r'[\\/*?:"<>|]', "_", p_name)
        t_cmp = str(
            st.session_state.get(
                f"v2_t_cmp_{dataset_key}_{p_name}", f"{p_name} — 多批次对比"
            )
        )
        t_hist_z = str(
            st.session_state.get(
                f"v2_t_hist_{dataset_key}_{p_name}",
                f"{p_name} — 多批次含组直方图",
            )
        )
        zf.writestr(
            f"{safe_p}/{safe_p}_多批次分布与CPK对比.png",
            render_multi_batch_comparison_from_map(
                batch_labels_all,
                bundles_by_project[p_name],
                t_cmp,
                show_outer_border,
            ),
        )
        zf.writestr(
            f"{safe_p}/{safe_p}_多批次含组直方图.png",
            render_grouped_histogram_from_map(
                batch_labels_all,
                bundles_by_project[p_name],
                t_hist_z,
                22,
                "频数 (Count)",
                True,
                True,
                show_outer_border,
            ),
        )
        for b_lbl, b_obj in bundles_by_project[p_name].items():
          safe_b = re.sub(r'[\\/*?:"<>|]', "_", b_lbl)
          zf.writestr(
              f"{safe_p}/{safe_b}/{safe_p}_{safe_b}_CPK.png",
              render_capability_from_bundle(
                  b_obj,
                  f"{p_name} [{b_lbl}] — Process Capability Report",
                  9.6,
                  7.2,
                  show_outer_border,
              ),
          )
    st.session_state[v2_zip_state_key] = zip_buf.getvalue()
    st.session_state[v2_zip_sig_key] = v2_cur_zip_sig

  if (
      st.session_state.get(v2_zip_state_key)
      and st.session_state.get(v2_zip_sig_key) == v2_cur_zip_sig
  ):
    st.download_button(
        "下载 ZIP 包",
        data=st.session_state[v2_zip_state_key],
        file_name="v2.0_多批次SPC对比图表包.zip",
        mime="application/zip",
        key=f"v2_dl_zip_{dataset_key}",
    )

  proj_tabs = st.tabs([f"📊 {p_name}" for p_name in ready_projects])
  for p_tab, p_name in zip(proj_tabs, ready_projects):
    with p_tab:
      p_batch_map = bundles_by_project[p_name]
      available_b_labels = [
          lbl for lbl in batch_labels_all if lbl in p_batch_map
      ]
      safe_p = re.sub(r'[\\/*?:"<>|]', "_", p_name)

      t_cmp_default = f"{p_name} — 多批次过程分布与 CPK 对比"
      t_hist_default = f"{p_name} — 多批次含组直方图"
      t_cap_default = f"{p_name} — Process Capability Report"
      t_box_default = f"{p_name} — Box Plot"
      t_mean_default = f"{p_name}均值对比"

      t_cmp = str(
          st.session_state.get(
              f"v2_t_cmp_{dataset_key}_{p_name}", t_cmp_default
          )
          or t_cmp_default
      )
      t_hist = str(
          st.session_state.get(
              f"v2_t_hist_{dataset_key}_{p_name}", t_hist_default
          )
          or t_hist_default
      )
      t_cap_prefix = str(
          st.session_state.get(
              f"v2_t_cap_{dataset_key}_{p_name}", t_cap_default
          )
          or t_cap_default
      )
      t_box_prefix = str(
          st.session_state.get(
              f"v2_t_box_{dataset_key}_{p_name}", t_box_default
          )
          or t_box_default
      )
      t_mean_title = str(
          st.session_state.get(
              f"v2_t_mean_{dataset_key}_{p_name}", t_mean_default
          )
          or t_mean_default
      )

      sub_cmp, sub_single, sub_data = st.tabs([
          "1️⃣ 多批次联合对比图",
          "2️⃣ 单批次明细图表（逐批检查）",
          "3️⃣ 各批次清洗明细导出",
      ])

      with sub_cmp:
        png_cmp = render_multi_batch_comparison_from_map(
            batch_labels_all, p_batch_map, t_cmp, show_outer_border
        )
        st.image(png_cmp, width=980)
        render_chart_action_bar(
            png_cmp,
            f"{safe_p}_MultiBatch_Compare.png",
            f"v2_cmp_{dataset_key}_{p_name}",
        )

        st.markdown("---")
        st.markdown("#### 📊 多批次含组直方图")
        hc1, hc2, hc3, hc4 = st.columns([1.2, 1.3, 1.2, 1.2])
        hist_bins = hc1.slider(
            "直方分组数 (Bins)",
            min_value=8,
            max_value=60,
            value=22,
            step=1,
            key=f"v2_hbins_{dataset_key}_{p_name}",
        )
        hist_y_metric = hc2.selectbox(
            "纵轴统计口径",
            options=["频数 (Count)", "概率密度 (Density)"],
            index=0,
            key=f"v2_hym_{dataset_key}_{p_name}",
        )
        show_fit_line = hc3.checkbox(
            "叠加正态拟合线",
            value=True,
            key=f"v2_hfit_{dataset_key}_{p_name}",
        )
        show_h_spec = hc4.checkbox(
            "显示规格线 (LSL/Tgt/USL)",
            value=True,
            key=f"v2_hspec_{dataset_key}_{p_name}",
        )

        png_hist = render_grouped_histogram_from_map(
            batch_labels_all,
            p_batch_map,
            t_hist,
            hist_bins,
            hist_y_metric,
            show_fit_line,
            show_h_spec,
            show_outer_border,
        )
        st.image(png_hist, width=980)
        render_chart_action_bar(
            png_hist,
            f"{safe_p}_Grouped_Histogram.png",
            f"v2_hist_{dataset_key}_{p_name}",
        )

        st.markdown("---")
        png_mt = render_multi_batch_mean_trend_from_map(
            batch_labels_all, p_batch_map, t_mean_title, show_outer_border
        )
        st.image(png_mt, width=1020)
        render_chart_action_bar(
            png_mt,
            f"{safe_p}_MultiBatch_MeanTrend.png",
            f"v2_mt_{dataset_key}_{p_name}",
        )

      with sub_single:
        chosen_b_lbl = st.selectbox(
            "选择要查看完整 SPC 图表的批次",
            options=available_b_labels,
            key=f"v2_pick_batch_{dataset_key}_{p_name}",
        )
        b_cur = p_batch_map[chosen_b_lbl]
        safe_b = re.sub(r'[\\/*?:"<>|]', "_", chosen_b_lbl)

        sc_left, sc_right = st.columns(2)
        with sc_left:
          png_b_cap = render_capability_from_bundle(
              b_cur,
              f"{t_cap_prefix} [{chosen_b_lbl}]",
              9.6,
              7.2,
              show_outer_border,
          )
          st.image(png_b_cap, width=640)
          render_chart_action_bar(
              png_b_cap,
              f"{safe_p}_{safe_b}_CPK.png",
              f"v2_bcap_{dataset_key}_{p_name}_{chosen_b_lbl}",
          )
        with sc_right:
          show_out_b = st.checkbox(
              "显示异常点",
              value=False,
              key=f"v2_bout_{dataset_key}_{p_name}_{chosen_b_lbl}",
          )
          png_b_box = render_box_from_bundle(
              b_cur,
              f"{t_box_prefix} [{chosen_b_lbl}]",
              9.6,
              6.4,
              show_out_b,
              False,
              False,
              4,
              show_outer_border,
          )
          st.image(png_b_box, width=640)
          render_chart_action_bar(
              png_b_box,
              f"{safe_p}_{safe_b}_Box.png",
              f"v2_bbox_{dataset_key}_{p_name}_{chosen_b_lbl}",
          )

      with sub_data:
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
          for b_lbl in available_b_labels:
            sh_name = re.sub(r'[\\/*?:\[\]]', "_", b_lbl)[:31]
            p_batch_map[b_lbl]["df_clean"].to_excel(
                writer, sheet_name=sh_name, index=False
            )
        excel_buf.seek(0)
        st.download_button(
            "下载完整 Excel",
            data=excel_buf,
            file_name=f"{safe_p}_各批次有效数据.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"v2_dl_xlsx_{dataset_key}_{p_name}",
        )
        show_all_v2_rows = st.checkbox(
            "显示全部行（默认仅预览各批次前 300 行以节省内存）",
            value=False,
            key=f"v2_show_all_rows_{dataset_key}_{p_name}",
        )
        for b_lbl in available_b_labels:
          df_show_b = p_batch_map[b_lbl]["df_clean"]
          st.caption(f"**{b_lbl}**（有效行：{len(df_show_b)}）")
          st.dataframe(
              df_show_b if show_all_v2_rows else df_show_b.head(300),
              width="stretch",
          )


# ==================== 路由分发 ====================
mode = st.session_state.get("app_mode", "home")
if mode == "v1":
  run_v1_app()
elif mode == "v2":
  run_v2_app()
else:
  render_landing_page()