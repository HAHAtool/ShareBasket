import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv
import hashlib
import secrets
import base64
import requests

# 初始化 Client
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# --- 核心安全邏輯：處理從 Google 跳轉回來的 Code ---
def handle_callback():
    params = st.query_params
    if "code" in params:
        # 從 Session 安全取得當初發出的 verifier
        # 這是符合 PKCE 標準的做法，確保 Code 只能由發起者交換
        code_verifier = st.session_state.get("code_verifier")
        
        if code_verifier:
            try:
                # 官方建議的交換方式
                supabase.auth.exchange_code_for_session({
                    "auth_code": params["code"],
                    "code_verifier": code_verifier
                })
                # 清理參數與臨時驗證碼
                st.query_params.clear()
                if "code_verifier" in st.session_state:
                    del st.session_state["code_verifier"]
                st.rerun()
            except Exception as e:
                st.error(f"安全驗證失敗: {e}")
        else:
            # 如果遺失了 verifier，嘗試靜默獲取（應對部分 SDK 自動處理情況）
            session = supabase.auth.get_session()
            if session:
                st.query_params.clear()
                st.rerun()

# --- 執行回傳攔截 ---
handle_callback()

# 獲取目前使用者
def get_user():
    try:
        res = supabase.auth.get_session()
        return res.user if res else None
    except:
        return None

user = get_user()

# --- UI 介面 ---
st.title("🛒 分食趣")

with st.sidebar:
    if user:
        st.success(f"已安全登入: {user.email}")
        if st.button("登出"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        if st.button("🚀 使用 Google 一鍵登入"):
            # 發起官方 OAuth 流程
            # flow_type 預設即為 pkce
            resp = supabase.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": st.secrets["REDIRECT_URI"],
                    "query_params": {"prompt": "select_account"}
                }
            })
            
            # 重要：SDK 在發起時會自動產生一個 verifier，我們必須把它攔截並存下來
            # 否則跳轉回來後，Python 會忘記它
            if resp.url:
                # 獲取 SDK 自動產生的 verifier
                # 注意：這取決於 supabase-py 的版本，通常在 client.auth 內部
                # 若自動獲取失敗，我們可以用 st.session_state 輔助
                st.session_state["code_verifier"] = supabase.auth._client.get_code_verifier()
                
                # 安全跳轉
                st.link_button("前往 Google 驗證", resp.url)

if user:
    st.write("### 認證成功")
    st.info("此 Session 已通過官方 PKCE 安全驗證。")
# --- 5. 主畫面標題與 Tab ---
st.title("🛒 分食趣-現場媒合")
tab1, tab2 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團"])

with tab1:
    try:
        res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").order("created_at", desc=True).execute()
        items = res.data
        if not items:
            st.info("目前現場沒有人發起分食。")
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
                                st.error("請先登入才能加入！")
                            else:
                                new_remain = item['remaining_units'] - 1
                                status = 'active' if new_remain > 0 else 'closed'
                                supabase.table("groups").update({"remaining_units": new_remain, "status": status}).eq("id", item['id']).execute()
                                st.success(f"✅ 成功加入！請與 {item['creator_nickname']} 聯繫。")
                                st.balloons()
                                st.rerun()
    except Exception as e:
        st.error(f"讀取失敗: {e}")

with tab2:
    if not user:
        st.warning("🛑 請先登入 Google 帳號。")
    else:
        if not st.session_state.confirm_publish:
            st.subheader("📢 第一步：填寫內容")
            stores_res = supabase.table("stores").select("*").execute().data
            store_map = {s['branch_name']: s['id'] for s in stores_res}
            selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
            
            pops = supabase.table("popular_items").select("*").execute().data
            item_name = st.selectbox("商品名稱", [p['name'] for p in pops])
            
            price = st.number_input("商品總價格", min_value=1, value=259)
            total_u = st.number_input("商品總包裝入數", min_value=1, value=12)
            
            col_my, col_others = st.columns(2)
            with col_my:
                my_stay = st.number_input("主揪自留數量", min_value=1, max_value=total_u, value=1)
            with col_others:
                others_get = total_u - my_stay
                st.metric("求分走數量", f"{others_get} 份")
            
            u_price = math.ceil(price / total_u)
            if st.button("📝 檢查發布內容", use_container_width=True):
                st.session_state.temp_post = {
                    "item": item_name, "price": price, "u_price": u_price,
                    "others": others_get, "my_stay": my_stay, "store_id": store_map[selected_store]
                }
                st.session_state.confirm_publish = True
                st.rerun()
        else:
            post = st.session_state.temp_post
            st.subheader("📢 第二步：確認發布")
            st.warning(f"確認：{post['item']} ${post['price']}，您留 {post['my_stay']} 份，求分 {post['others']} 份？")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("❌ 修改內容"):
                    st.session_state.confirm_publish = False
                    st.rerun()
            with c2:
                if st.button("✅ 正式發布", type="primary"):
                    new_data = {
                        "creator_id": user.id,
                        "creator_nickname": user.email.split('@')[0],
                        "store_id": post['store_id'],
                        "item_name": post['item'],
                        "total_price": post['price'],
                        "total_units": post['my_stay'] + post['others'],
                        "unit_price": post['u_price'],
                        "remaining_units": post['others'],
                        "creator_stay_units": post['my_stay']
                    }
                    supabase.table("groups").insert(new_data).execute()
                    # 指定成功訊息格式
                    st.success(f"🎉 {post['item']} ${post['price']} 求分 {post['others']} 顆發布成功！")
                    st.balloons()
                    st.session_state.confirm_publish = False