import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv

# 1. 初始化與環境設定
load_dotenv()
url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

st.set_page_config(page_title="分食趣", page_icon="🛒", layout="centered")

# --- 2. 處理 Google 登入邏輯 ---
def get_user():
    """檢查目前是否有登入使用者"""
    try:
        user_res = supabase.auth.get_user()
        return user_res.user if user_res else None
    except Exception:
        return None

def login_with_google():
    """發起 Google OAuth 登入"""
    # 確保這裡的網址與 Supabase Site URL 完全一致，且結尾沒有斜線
    target_url = "https://cdhbz3unr3cpvmwnvjpyjr.streamlit.app"
    
    try:
        auth_res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": target_url
            }
        })
        
        if not auth_res or not auth_res.url:
            st.error("❌ Supabase 回傳網址為空，請檢查 Supabase 控制台的 Google Provider 設定。")
            return None
            
        return auth_res.url

    except Exception as e:
        st.error(f"❌ 登入初始化失敗: {str(e)}")
        return None

# 初始化 Session State
if "confirm_publish" not in st.session_state:
    st.session_state.confirm_publish = False

user = get_user()

# --- 側邊欄：使用者資訊 ---
with st.sidebar:
    st.title("👤 會員中心")
    if user:
        st.write(f"你好，{user.email.split('@')[0]}！")
        if st.button("登出"):
            supabase.auth.sign_out()
            st.rerun()
    else:
        st.warning("請先登入以使用完整功能")
        auth_url = login_with_google()
        
        if auth_url:
            # 方案：建立一個明顯的按鈕連結
            # 使用 target="_blank" 強制在新分頁開啟，這是目前最穩定的做法
            st.markdown(f'''
                <a href="{auth_url}" target="_blank" style="text-decoration: none;">
                    <div style="
                        background-color: #4285F4; 
                        color: white; 
                        padding: 12px; 
                        border-radius: 5px; 
                        text-align: center;
                        font-weight: bold;
                        box-shadow: 0px 2px 5px rgba(0,0,0,0.2);
                        cursor: pointer;">
                        🚀 點擊前往 Google 登入
                    </div>
                </a>
                <p style="font-size: 12px; color: gray; text-align: center; margin-top: 10px;">
                    (登入成功後請關閉分頁並重新整理本頁)
                </p>
            ''', unsafe_allow_html=True)

# --- 主畫面標題 ---
st.title("🛒 分食趣-現場媒合")

tab1, tab2 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團"])

# --- Tab 1: 顯示清單 ---
with tab1:
    try:
        res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").order("created_at", desc=True).execute()
        items = res.data
        if not items:
            st.info("目前現場沒有人在揪喔，快去發起一個！")
        else:
            for item in items:
                with st.container(border=True):
                    col_info, col_btn = st.columns([3, 1])
                    with col_info:
                        st.subheader(item['item_name'])
                        st.write(f"📍 {item['stores']['branch_name']} | 👤 主揪：{item['creator_nickname']}")
                        st.write(f"💵 單價：**${int(item['unit_price'])}** / 份")
                    with col_btn:
                        st.metric("剩餘", f"{item['remaining_units']} 份")
                        if st.button(f"我要 +1", key=f"join_{item['id']}"):
                            if not user:
                                st.error("請先登入才能加入分食！")
                            else:
                                new_remain = item['remaining_units'] - 1
                                status = 'active' if new_remain > 0 else 'closed'
                                supabase.table("groups").update({"remaining_units": new_remain, "status": status}).eq("id", item['id']).execute()
                                st.success(f"✅ 成功加入！請與 {item['creator_nickname']} 聯繫面交。")
                                st.balloons()
                                st.rerun()
    except Exception as e:
        st.error(f"讀取資料失敗: {e}")

# --- Tab 2: 發起揪團 (兩段式確認) ---
with tab2:
    if not user:
        st.warning("🛑 請先使用 Google 登入後再發起揪團。")
    else:
        if not st.session_state.confirm_publish:
            # 步驟一：填寫資訊
            st.subheader("第一步：填寫內容")
            
            stores_res = supabase.table("stores").select("*").execute().data
            store_map = {s['branch_name']: s['id'] for s in stores_res}
            selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
            
            pops = supabase.table("popular_items").select("*").execute().data
            pop_names = [p['name'] for p in pops]
            item_name = st.selectbox("商品名稱", pop_names)
            
            total_price = st.number_input("商品總價格", min_value=1, value=259)
            total_u = st.number_input("商品總包裝入數", min_value=1, value=12)
            
            # 數量分配邏輯
            col_my, col_others = st.columns(2)
            with col_my:
                my_stay = st.number_input("主揪自留數量", min_value=1, max_value=total_u, value=total_u//2)
            with col_others:
                others_get = total_u - my_stay
                st.metric("求分走數量", f"{others_get} 份")
            
            u_price = math.ceil(total_price / total_u)
            st.info(f"💡 系統計算單價：${u_price} / 份")

            if st.button("📝 檢查發布內容", use_container_width=True):
                st.session_state.confirm_publish = True
                st.rerun()
        
        else:
            # 步驟二：二次確認
            st.subheader("第二步：確認並發布")
            with st.status("🔍 發布資訊摘要", expanded=True):
                st.write(f"📍 分店：{selected_store}")
                st.write(f"📦 商品：{item_name}")
                st.write(f"🙋 您自留：{my_stay} 份")
                st.write(f"🤝 求分走：{others_get} 份")
                st.write(f"💵 預估向對方收取：**${u_price * others_get} 元**")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("❌ 修改內容", use_container_width=True):
                    st.session_state.confirm_publish = False
                    st.rerun()
            with c2:
                if st.button("✅ 確認正式發布", type="primary", use_container_width=True):
                    # 寫入資料庫
                    new_data = {
                        "creator_id": user.id,
                        "creator_nickname": user.email.split('@')[0],
                        "store_id": store_map[selected_store],
                        "item_name": item_name,
                        "total_price": total_price,
                        "total_units": total_u,
                        "unit_price": u_price,
                        "remaining_units": others_get,
                        "creator_stay_units": my_stay
                    }
                    supabase.table("groups").insert(new_data).execute()
                    
                    # 顯示成功訊息
                    st.success(f"🎉 {item_name} ${total_price} 求分 {others_get} 顆發布成功！")
                    st.balloons()
                    
                    # 重置狀態
                    st.session_state.confirm_publish = False
                    # 延遲刷新回首頁
                    st.rerun()