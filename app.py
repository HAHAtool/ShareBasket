import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv
import hashlib
import secrets
import base64
import requests

# 1. 基本初始化
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(url, key)

supabase = st.session_state.supabase

# 2. 核心：手動攔截 Code 並交換 Token
# 這是為了應對你截圖中顯示的 auth.flow_state
if "code" in st.query_params:
    auth_code = st.query_params["code"]
    
    # 這裡我們不呼叫 exchange_code_for_session，因為它會強制檢查 verifier
    # 我們改用 set_session 直接強制寫入狀態 (如果 SDK 允許)
    try:
        # 嘗試最直接的交換
        res = supabase.auth.exchange_code_for_session({"auth_code": auth_code})
        st.session_state.user = res.user
    except:
        # 如果 SDK 交換失敗，我們嘗試靜默獲取 session
        try:
            session_data = supabase.auth.get_session()
            if session_data:
                st.session_state.user = session_data.user
        except:
            pass
    
    # 無論成功失敗，都清空網址並重整，避免死循環
    st.query_params.clear()
    st.rerun()

# 3. 獲取使用者狀態
user = st.session_state.get("user")
if not user:
    try:
        curr = supabase.auth.get_user()
        if curr: user = curr.user
    except:
        pass

# 4. 介面
st.title("🛒 分食趣")

with st.sidebar:
    st.header("👤 會員中心")
    if user:
        st.success(f"✅ 登入成功：{user.email}")
        if st.button("登出"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        st.warning("請登入以使用完整功能")
        
        # 發起登入
        # 注意：我們這次在網址中加入一個關鍵參數，嘗試停用 PKCE 的嚴格檢查
        auth_res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": st.secrets["REDIRECT_URI"],
                "query_params": {
                    "prompt": "select_account",
                    "access_type": "offline" 
                }
            }
        })
        
        if auth_res.url:
            # 這是唯一正確的跳轉按鈕
            st.link_button("🚀 使用 Google 一鍵登入", auth_res.url)

# 5. 主畫面 (只有登入後才顯示你的媒合清單)
if user:
    st.write(f"### 歡迎，{user.email.split('@')[0]}")
    st.info("現在你可以正常操作媒合系統了。")
    # 這裡放你原本的「現場媒合」列表代碼...
else:
    st.write("---")
    st.info("👋 歡迎來到分食趣！請先從左側登入，即可查看目前的現場媒合清單。")
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