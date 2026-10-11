from datetime import date
import time
import gspread
import pandas as pd
import streamlit as st

# 頁面配置
st.set_page_config(
    page_title="學生訓練紀錄管理系統 (Google Sheets)",
    page_icon="📝",
    layout="wide",
)

# ------------------------------------------------------------------------------
# 1. 建立 Google Sheets 連線與工具函數
# ------------------------------------------------------------------------------
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1sdvmR4ou6AyWFBtckO8jtvC-NVsF2VkBGaZXGWNlu7k/edit?gid=0#gid=0"


@st.cache_resource
def get_spreadsheet():
  scopes = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  if "gcp_service_account" in st.secrets:
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "\\n" in creds_dict.get("private_key", ""):
      creds_dict["private_key"] = creds_dict["private_key"].replace(
          "\\n", "\n"
      )
    gc = gspread.service_account_from_dict(creds_dict, scopes=scopes)
  else:
    gc = gspread.service_account(filename="credentials.json", scopes=scopes)
  return gc.open_by_url(SPREADSHEET_URL)


sh = get_spreadsheet()


# 核心優化：加上 ttl 快取，15 秒內同一個分頁只打 1 次 Google API，徹底解決 429 限制！
@st.cache_data(ttl=15, show_spinner=False)
def load_data(worksheet_name):
  """穩健讀取工作表資料，支援自動重試與快取"""
  for attempt in range(3):
    try:
      ws = sh.worksheet(worksheet_name)
      data = ws.get_all_values()
      if not data or len(data) <= 1:
        return pd.DataFrame()
      header = [str(col).strip() for col in data[0]]
      rows = data[1:]
      df = pd.DataFrame(rows, columns=header)
      return df.dropna(how="all")
    except Exception as e:
      if "429" in str(e) and attempt < 2:
        time.sleep(1.5 * (attempt + 1))
        continue
      st.sidebar.error(f"讀取 {worksheet_name} 失敗: {e}")
      return pd.DataFrame()
  return pd.DataFrame()


def save_data(df, worksheet_name):
  """覆寫指定工作表資料，並在完成後立即清除快取"""
  for attempt in range(3):
    try:
      try:
        ws = sh.worksheet(worksheet_name)
      except Exception:
        ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)

      ws.clear()
      if not df.empty:
        values = [df.columns.values.tolist()] + df.values.tolist()
        ws.update(range_name="A1", values=values)
      # 寫入成功後，清除快取確保下次讀取為最新版
      load_data.clear()
      break
    except Exception as e:
      if "429" in str(e) and attempt < 2:
        time.sleep(2 * (attempt + 1))
        continue
      st.error(f"寫入 {worksheet_name} 失敗: {e}")
      break


# 初始化基本動作庫（若為空才寫入）
exercises_df = load_data("exercises")
if exercises_df.empty or "name" not in exercises_df.columns:
  default_exercises = pd.DataFrame([
      {"name": "槓鈴臥推", "category": "上肢"},
      {"name": "槓鈴划船", "category": "上肢"},
      {"name": "啞鈴肩推", "category": "上肢"},
      {"name": "滑輪下拉", "category": "上肢"},
      {"name": "槓鈴深蹲", "category": "下肢"},
      {"name": "槓鈴硬舉", "category": "下肢"},
      {"name": "保加利亞分腿蹲", "category": "下肢"},
      {"name": "羅馬尼亞硬舉", "category": "下肢"},
  ])
  save_data(default_exercises, "exercises")
  exercises_df = default_exercises

# ------------------------------------------------------------------------------
# 2. 側邊欄：學生列表選擇與名單擴充
# ------------------------------------------------------------------------------
st.sidebar.title("👥 學生管理")

# 側邊欄手動重整按鈕
if st.sidebar.button("🔄 同步 Google Sheets 最新資料", use_container_width=True):
  load_data.clear()
  st.rerun()

students_df = load_data("students")
student_list = []

name_col = None
if not students_df.empty:
  if "name" in students_df.columns:
    name_col = "name"
  elif "姓名" in students_df.columns:
    name_col = "姓名"

if name_col:
  student_list = sorted([
      s
      for s in students_df[name_col].dropna().astype(str).unique().tolist()
      if s.strip()
  ])

# 新增學生功能
with st.sidebar.expander("➕ 新增學生姓名"):
  new_student = st.text_input("輸入新學生姓名")
  if st.button("確認新增學生"):
    name_clean = new_student.strip()
    if name_clean:
      if name_clean in student_list:
        st.sidebar.warning("該學生姓名已存在！")
      else:
        new_row = pd.DataFrame([{"name": name_clean}])
        if not students_df.empty and name_col:
          updated_students = pd.concat(
              [
                  students_df[[name_col]].rename(columns={name_col: "name"}),
                  new_row,
              ],
              ignore_index=True,
          )
        else:
          updated_students = new_row
        save_data(updated_students, "students")
        st.sidebar.success(f"已成功新增：{name_clean}")
        st.rerun()
    else:
      st.sidebar.error("姓名不能為空白！")

# 擴充動作項目
with st.sidebar.expander("🏋 新增動作項目"):
  new_exercise = st.text_input("輸入新動作名稱")
  new_cat = st.selectbox("動作分類", ["上肢", "下肢", "核心", "全身/其他"])
  if st.button("確認新增動作"):
    ex_clean = new_exercise.strip()
    current_exercises = (
        exercises_df["name"].tolist() if "name" in exercises_df.columns else []
    )
    if ex_clean:
      if ex_clean in current_exercises:
        st.sidebar.warning("該動作名稱已存在！")
      else:
        new_ex_row = pd.DataFrame([{"name": ex_clean, "category": new_cat}])
        updated_exercises = pd.concat(
            [exercises_df, new_ex_row], ignore_index=True
        )
        save_data(updated_exercises, "exercises")
        st.sidebar.success(f"已成功新增：{ex_clean}")
        st.rerun()
    else:
      st.sidebar.error("動作名稱不能為空白！")

if not student_list:
  st.info(
      "👈 目前 Google Sheets 內尚未讀取到學生名單，請先在左側邊欄新增學生姓名！"
  )
  st.stop()

selected_student = st.sidebar.radio("選擇要記錄的學生：", student_list)

# ------------------------------------------------------------------------------
# 3. 主畫面：選定學生的訓練紀錄、歷史日誌與 1RM 追蹤
# ------------------------------------------------------------------------------
head_col1, head_col2 = st.columns([3, 1])
with head_col1:
  st.title(f"📋 {selected_student} 的訓練日誌")
with head_col2:
  if st.button("🔄 同步刷新", key="top_refresh_btn", use_container_width=True):
    load_data.clear()
    st.rerun()

tab1, tab2, tab3 = st.tabs(
    ["✍️ 記錄當日訓練", "📊 歷史單日彙總", "🏆 三項 1RM 進步追蹤"]
)

exercise_options = (
    exercises_df["name"].dropna().tolist()
    if "name" in exercises_df.columns
    else []
)

# 一次性讀取全體 workout_logs，避免在每個 Tab 重複向 Google 發送請求
all_logs = load_data("workout_logs")
s_col = (
    "student_name"
    if "student_name" in all_logs.columns
    else ("學生姓名" if "學生姓名" in all_logs.columns else None)
)
d_col = (
    "log_date"
    if "log_date" in all_logs.columns
    else ("訓練日期" if "訓練日期" in all_logs.columns else None)
)

# ==================== Tab 1: 記錄當日訓練 ====================
with tab1:
  col_date, _ = st.columns([1, 2])
  with col_date:
    training_date = st.date_input("訓練日期", value=date.today())

  date_str = str(training_date)
  st.subheader(f"記錄 {date_str} 的動作組數")

  # Session State 初始化
  if "current_ex" not in st.session_state:
    st.session_state["current_ex"] = (
        exercise_options[0] if exercise_options else ""
    )
  if "current_set" not in st.session_state:
    st.session_state["current_set"] = 1
  if "last_weight" not in st.session_state:
    st.session_state["last_weight"] = 60.0
  if "last_reps" not in st.session_state:
    st.session_state["last_reps"] = 8

  def on_exercise_change():
    st.session_state["current_ex"] = st.session_state["select_ex_box"]
    st.session_state["current_set"] = 1

  current_idx = 0
  if st.session_state["current_ex"] in exercise_options:
    current_idx = exercise_options.index(st.session_state["current_ex"])

  st.selectbox(
      "選擇訓練動作（切換動作時組數將自動歸 1）",
      exercise_options,
      index=current_idx,
      key="select_ex_box",
      on_change=on_exercise_change,
  )

  active_ex = st.session_state["current_ex"]

  # 表單輸入
  with st.form("set_form", clear_on_submit=False):
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
      set_num = st.number_input(
          "第幾組 (Set)",
          min_value=1,
          max_value=30,
          value=st.session_state["current_set"],
          step=1,
      )
    with c2:
      weight = st.number_input(
          "重量 (kg)",
          min_value=0.0,
          max_value=500.0,
          value=float(st.session_state["last_weight"]),
          step=0.5,
      )
    with c3:
      reps = st.number_input(
          "次數 (Reps)",
          min_value=1,
          max_value=100,
          value=int(st.session_state["last_reps"]),
          step=1,
      )
    with c4:
      note = st.text_input("備註 (RPE/握距/調整)", placeholder="選填，例如 RPE 8")

    submitted = st.form_submit_button(
        f"💾 儲存【{active_ex}】第 {set_num} 組", use_container_width=True
    )

    if submitted:
      new_log = pd.DataFrame([{
          "student_name": selected_student,
          "log_date": date_str,
          "exercise_name": active_ex,
          "set_num": int(set_num),
          "weight": float(weight),
          "reps": int(reps),
          "note": str(note) if note else "",
      }])
      updated_logs = pd.concat([all_logs, new_log], ignore_index=True)
      save_data(updated_logs, "workout_logs")

      st.session_state["current_set"] = set_num + 1
      st.session_state["last_weight"] = weight
      st.session_state["last_reps"] = reps
      st.success(
          f"已寫入 Google Sheets：{active_ex} 第 {set_num} 組 - {weight} kg x"
          f" {reps} 次"
      )
      st.rerun()

  # 今日已完成組數
  st.divider()
  st.subheader(f"📅 {date_str} 今日已完成組數（可直接在表格內修改或刪除）")

  if not all_logs.empty and s_col and d_col:
    today_mask = (all_logs[s_col].astype(str) == selected_student) & (
        all_logs[d_col].astype(str) == date_str
    )
    today_df = all_logs[today_mask].copy().reset_index(drop=True)
  else:
    today_df = pd.DataFrame()

  if not today_df.empty:
    display_cols = ["exercise_name", "set_num", "weight", "reps", "note"]
    for col in display_cols:
      if col not in today_df.columns:
        today_df[col] = ""

    today_df["set_num"] = (
        pd.to_numeric(today_df["set_num"], errors="coerce")
        .fillna(1)
        .astype(int)
    )
    today_df["weight"] = (
        pd.to_numeric(today_df["weight"], errors="coerce")
        .fillna(0.0)
        .astype(float)
    )
    today_df["reps"] = (
        pd.to_numeric(today_df["reps"], errors="coerce").fillna(1).astype(int)
    )

    edited_df = st.data_editor(
        today_df[display_cols],
        column_config={
            "exercise_name": st.column_config.SelectboxColumn(
                "動作名稱", options=exercise_options, required=True
            ),
            "set_num": st.column_config.NumberColumn(
                "組數", min_value=1, max_value=30, step=1, required=True
            ),
            "weight": st.column_config.NumberColumn(
                "重量 (kg)",
                min_value=0.0,
                max_value=500.0,
                step=0.5,
                required=True,
            ),
            "reps": st.column_config.NumberColumn(
                "次數", min_value=1, max_value=100, step=1, required=True
            ),
            "note": st.column_config.TextColumn("備註"),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="today_editor",
    )

    if st.button("💾 儲存修改至 Google Sheets", type="primary"):
      other_logs = all_logs[~today_mask].copy()
      clean_edited = edited_df.dropna(subset=["exercise_name"]).copy()
      clean_edited["student_name"] = selected_student
      clean_edited["log_date"] = date_str
      clean_edited["set_num"] = clean_edited["set_num"].astype(int)
      clean_edited["weight"] = clean_edited["weight"].astype(float)
      clean_edited["reps"] = clean_edited["reps"].astype(int)
      clean_edited["note"] = clean_edited["note"].fillna("").astype(str)

      final_logs = pd.concat([other_logs, clean_edited], ignore_index=True)
      save_data(final_logs, "workout_logs")
      st.success("Google Sheets 今日組數已成功更新！")
      st.rerun()
  else:
    st.caption("今天尚未新增任何組數紀錄。")

# ==================== Tab 2: 歷史單日彙總 ====================
with tab2:
  st.subheader(f"📈 {selected_student} 的歷史累積紀錄（單日動作彙總）")

  if not all_logs.empty and s_col:
    student_logs = all_logs[
        all_logs[s_col].astype(str) == selected_student
    ].copy()
  else:
    student_logs = pd.DataFrame()

  if not student_logs.empty:
    student_logs["weight"] = pd.to_numeric(
        student_logs["weight"], errors="coerce"
    ).fillna(0)
    student_logs["reps"] = pd.to_numeric(
        student_logs["reps"], errors="coerce"
    ).fillna(0)
    student_logs["set_num"] = pd.to_numeric(
        student_logs["set_num"], errors="coerce"
    ).fillna(1)

    summary_df = (
        student_logs.groupby(["log_date", "exercise_name"])
        .agg(
            當日總組數=("set_num", "count"),
            平均重量_kg=("weight", lambda x: round(x.mean(), 1)),
            平均次數=("reps", lambda x: round(x.mean(), 1)),
        )
        .reset_index()
        .rename(columns={"log_date": "日期", "exercise_name": "動作名稱"})
    )

    summary_df = summary_df.sort_values(
        by=["日期", "動作名稱"], ascending=[False, True]
    )

    filter_ex = st.selectbox(
        "篩選動作：", ["全部"] + list(summary_df["動作名稱"].unique())
    )

    if filter_ex != "全部":
      view_df = summary_df[summary_df["動作名稱"] == filter_ex].copy()
      st.dataframe(view_df, use_container_width=True)
      st.line_chart(data=view_df.sort_values("日期"), x="日期", y="平均重量_kg")
    else:
      st.dataframe(summary_df, use_container_width=True)

    csv = summary_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"⬇️ 匯出 {selected_student} 的歷史單日彙總日誌 (CSV)",
        data=csv,
        file_name=f"{selected_student}_歷史單日動作彙總.csv",
        mime="text/csv",
    )
  else:
    st.info("該學生尚無歷史紀錄。")

# ==================== Tab 3: 三項 1RM 進步追蹤 ====================
with tab3:
  st.subheader(f"🏆 {selected_student} 的 SBD 三項推估 1RM 進步追蹤")
  st.caption(
      "💡 推估公式採用 Epley 公式：`重量 × (1 + 次數 / 30)`，次數為 1 時即為實測 1RM。"
  )

  # 嚴格精準比對這三個動作
  target_exercises = ["槓鈴深蹲", "相撲硬舉", "槓鈴臥推"]

  if not student_logs.empty and "exercise_name" in student_logs.columns:
    sbd_logs = student_logs[
        student_logs["exercise_name"].isin(target_exercises)
    ].copy()
  else:
    sbd_logs = pd.DataFrame()

  if not sbd_logs.empty:
    sbd_logs["e1RM"] = sbd_logs.apply(
        lambda r: (
            r["weight"]
            if r["reps"] == 1
            else round(r["weight"] * (1 + r["reps"] / 30.0), 1)
        ),
        axis=1,
    )

    idx_max = sbd_logs.groupby(["log_date", "exercise_name"])["e1RM"].idxmax()
    daily_max_df = sbd_logs.loc[idx_max].copy().sort_values("log_date")

    col_sq, col_dl, col_bp = st.columns(3)
    cards = [
        ("槓鈴深蹲", col_sq, "🏋️ 深蹲 PR"),
        ("相撲硬舉", col_dl, "⚡ 相撲硬舉 PR"),
        ("槓鈴臥推", col_bp, "💪 臥推 PR"),
    ]

    for ex_name, col_obj, label_text in cards:
      ex_data = daily_max_df[daily_max_df["exercise_name"] == ex_name]
      with col_obj:
        if not ex_data.empty:
          best_1rm = ex_data["e1RM"].max()
          best_row = ex_data[ex_data["e1RM"] == best_1rm].iloc[0]
          col_obj.metric(
              label=label_text,
              value=f"{best_1rm} kg",
              help=(
                  f"於 {best_row['log_date']} 達成 ({best_row['weight']}kg x"
                  f" {best_row['reps']}下)"
              ),
          )
        else:
          col_obj.metric(label=label_text, value="尚無資料")

    st.divider()

    st.subheader("📊 1RM 進步趨勢長條圖")
    # 將資料轉為長表，並使用 stack=False 讓同天不同動作並排分開，不再疊在一起
    st.bar_chart(
        data=daily_max_df,
        x="log_date",
        y="e1RM",
        color="exercise_name",
        stack=False,
    )

    st.subheader("📋 三項訓練課最高表現紀錄明細")
    display_sbd = daily_max_df.rename(
        columns={
            "log_date": "訓練日期",
            "exercise_name": "動作名稱",
            "weight": "當日最高組重量 (kg)",
            "reps": "次數",
            "e1RM": "當日推估 1RM (kg)",
        }
    )[
        [
            "訓練日期",
            "動作名稱",
            "當日最高組重量 (kg)",
            "次數",
            "當日推估 1RM (kg)",
        ]
    ].sort_values(by=["訓練日期", "動作名稱"], ascending=[False, True])
    st.dataframe(display_sbd, use_container_width=True)
  else:
    st.info(
        "目前尚未記錄到任何「槓鈴深蹲」、「相撲硬舉」或「槓鈴臥推」的組數資料。"
    )
