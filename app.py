import streamlit as st
import pandas as pd
import numpy as np
import pymysql
import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 設置頁面標題
st.title('Rack電流分析')

# 從 secrets.toml 讀取 MySQL 連接資訊
# @st.cache_resource
def get_connection():
    try:
        conn = pymysql.connect(
            host=st.secrets["mysql"]["host"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
            port=int(st.secrets["mysql"].get("port", 3306))
        )
        return conn
    except Exception as e:
        st.error(f"資料庫連接錯誤: {e}")
        return None

# 使用者驗證函數
def authenticate_user(user_id):
    try:
        conn = get_connection()
        if conn:
            with conn.cursor() as cursor:
                # 查詢用戶表中是否存在該ID
                query = "SELECT id, name FROM user WHERE id = %s"
                cursor.execute(query, [user_id])
                result = cursor.fetchone()
                conn.close()
                return result
        return None
    except Exception as e:
        st.error(f"驗證使用者時發生錯誤: {e}")
        return None

# 初始化 session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""

# 使用者驗證區塊
if not st.session_state.authenticated:
    st.subheader("使用者驗證")
    user_id = st.text_input("請輸入您的ID")
    
    if st.button("登入"):
        if user_id:
            user_info = authenticate_user(user_id)
            if user_info:
                user_id, user_name = user_info
                st.session_state.authenticated = True
                st.session_state.user_name = user_name
                st.success(f"歡迎回來，{user_name}！")
                st.rerun()
            else:
                st.error("無效的ID，請重試。")
        else:
            st.warning("請輸入ID。")
else:
    # 顯示歡迎信息
    st.subheader(f"歡迎，{st.session_state.user_name}！")
    
    if st.button("登出"):
        st.session_state.authenticated = False
        st.session_state.user_name = ""
        st.rerun()
    
    # 使用者輸入區域
    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input("起始日期", datetime.date.today() - datetime.timedelta(days=1))
        start_time = st.time_input("起始時間", datetime.time(0, 0))
        
    with col2:
        end_date = st.date_input("結束日期", datetime.date.today())
        end_time = st.time_input("結束時間", datetime.time(0, 0))

    # 合併日期和時間
    start_datetime = datetime.datetime.combine(start_date, start_time)
    end_datetime = datetime.datetime.combine(end_date, end_time)

    # 電流區間大小設定
    current_bin_size = st.slider("電流區間大小 (A)", min_value=5.0, max_value=30.0, value=5.0, step=1.0)

    # 選擇Rack ID
    rack_ids = range(1,13)
    selected_rack = st.selectbox("選擇Rack ID", rack_ids)

    # 查詢按鈕
    if st.button("查詢資料") and selected_rack:
        if start_datetime >= end_datetime:
            st.error("起始時間必須早於結束時間")
        else:
            try:
                conn = get_connection()
                query = """
                SELECT Timestamp, Rack_ID, Rack_Current 
                FROM rack
                WHERE Rack_ID = %s AND Timestamp >= %s AND Timestamp < %s
                ORDER BY Timestamp
                """
                with conn.cursor() as cursor:
                    cursor.execute(query, [selected_rack, start_datetime, end_datetime])
                    results = cursor.fetchall()
                    df = pd.DataFrame(results, columns=["Timestamp", "Rack_ID", "Rack_Current"])
                    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
                
                if df.empty:
                    st.warning("查詢時間範圍內沒有資料")
                else:
                    st.success(f"成功讀取 {len(df)} 筆資料")
                    
                    # 顯示資料摘要
                    st.subheader("資料摘要")
                    st.write(f"資料時間範圍: {df['Timestamp'].min()} 至 {df['Timestamp'].max()}")
                    st.write(f"電流範圍: {df['Rack_Current'].min():.2f}A 至 {df['Rack_Current'].max():.2f}A")
                    st.write(f"平均電流: {df['Rack_Current'].mean():.2f}A")
                    
                    # 將時間戳轉換為日期
                    df['Date'] = df['Timestamp'].dt.date
                    
                    # 獲取唯一日期列表
                    unique_dates = df['Date'].unique()
                    
                    # 創建每天的直方圖
                    st.subheader(f"Rack {selected_rack} 每日電流分布直方圖")
                    
                    # 計算電流的最小值和最大值，用於設置一致的 bin 範圍
                    min_current = df['Rack_Current'].min()
                    max_current = df['Rack_Current'].max()
                    
                    # 確保最大值略大於實際最大值，以包含所有數據
                    max_current = max_current + current_bin_size
                    
                    # 創建 bin 範圍 - 根據電流區間大小
                    bins = np.arange(min_current - (min_current % current_bin_size), 
                                    max_current + current_bin_size, 
                                    current_bin_size)
                    
                    # 創建標籤，顯示每個區間
                    bin_labels = [f"{bins[i]:.0f}A~{bins[i+1]:.0f}A" for i in range(len(bins)-1)]
                    
                    # 計算每個日期的行數，用於確定子圖的行數
                    n_days = len(unique_dates)
                    if n_days > 0:
                        if n_days == 1:
                            # 如果只有一天，創建單個圖
                            day_data = df[df['Date'] == unique_dates[0]]
                            
                            # 計算直方圖數據
                            counts, edges = np.histogram(day_data['Rack_Current'], bins=bins)
                            
                            # 使用 Plotly 創建直方圖
                            fig = go.Figure()
                            fig.add_trace(go.Bar(
                                x=[f"{bins[i]:.0f}A~{bins[i+1]:.0f}A" for i in range(len(bins)-1)],
                                y=counts,
                                marker_color='royalblue',
                                marker_line_color='rgb(8,48,107)',
                                marker_line_width=1.5
                            ))
                            
                            fig.update_layout(
                                title=f'日期: {unique_dates[0]}',
                                xaxis_title='電流區間 (A)',
                                yaxis_title='次數',
                                bargap=0.1,
                                height=500,
                                width=800
                            )
                            
                            st.plotly_chart(fig)
                        else:
                            # 多於一天，創建多個子圖
                            n_cols = min(2, n_days)  # 每行最多2個圖
                            n_rows = (n_days + n_cols - 1) // n_cols  # 向上取整
                            
                            # 使用 Plotly 的 subplot 功能
                            fig = make_subplots(
                                rows=n_rows, 
                                cols=n_cols,
                                subplot_titles=[f'日期: {date}' for date in unique_dates],
                                vertical_spacing=0.1
                            )
                            
                            # 為每一天創建直方圖
                            for i, date in enumerate(unique_dates):
                                row = i // n_cols + 1
                                col = i % n_cols + 1
                                
                                # 篩選當天的數據
                                day_data = df[df['Date'] == date]
                                
                                # 計算直方圖數據
                                counts, edges = np.histogram(day_data['Rack_Current'], bins=bins)
                                
                                # 添加到子圖
                                fig.add_trace(
                                    go.Bar(
                                        x=[f"{bins[i]:.0f}A~{bins[i+1]:.0f}A" for i in range(len(bins)-1)],
                                        y=counts,
                                        marker_color='royalblue',
                                        marker_line_color='rgb(8,48,107)',
                                        marker_line_width=1.5,
                                        name=f'{date}'
                                    ),
                                    row=row, col=col
                                )
                                
                                # 更新軸標題
                                fig.update_xaxes(title_text='電流區間 (A)', row=row, col=col)
                                fig.update_yaxes(title_text='次數', row=row, col=col)
                            
                            # 更新整體佈局
                            fig.update_layout(
                                height=400 * n_rows,
                                width=900,
                                showlegend=False,
                                title_text=f"Rack {selected_rack} 每日電流分布直方圖"
                            )
                            
                            st.plotly_chart(fig)
                    else:
                        st.warning("沒有足夠的日期資料來繪製直方圖")
                    
                    # 顯示原始資料表格
                    st.subheader("原始資料")
                    st.dataframe(df)
                    
                    # 提供下載功能
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="下載 CSV 資料",
                        data=csv,
                        file_name=f'rack_{selected_rack}_data_{start_date}_{end_date}.csv',
                        mime='text/csv',
                    )
                    
            except Exception as e:
                st.error(f"查詢資料時發生錯誤: {e}")
                st.error(f"錯誤詳情: {str(e)}")
            finally:
                if conn:
                    conn.close()

    # 頁面底部說明
    st.markdown("---")
    st.markdown("### 使用說明")
    st.markdown("""
    1. 選擇起始和結束日期時間範圍
    2. 設定電流區間大小
    3. 選擇Rack ID
    4. 點擊「查詢資料」按鈕生成分析結果
    """)
