import streamlit as st
from supabase import create_client
import math

# 1. 基礎連線
if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = st.session_state.supabase

# 初始化狀態
if "confirm_publish" not in st.session_state: st.session_state.confirm_publish = False
if "temp_post" not in st.session_state: st.session_state.temp_post = None

# --- 2. 核心邏輯函數 ---

def get_user():
    """獲取目前登入使用者"""
    if "user_obj" in st.session_state: return st.session_state.user_obj
    try:
        res = supabase.auth.get_session()
        if res and res.session:
            st.session_state.user_obj = res.user
            return res.user
    except: pass
    return None

def get_nickname(uid):
    """獲取用戶暱稱"""
    try:
        res = supabase.table("profiles").select("nickname").eq("id", uid).maybe_single().execute()
        return res.data['nickname'] if res.data else "神秘分食友"
    except: return "未知用戶"

@st.fragment(run_every="10s")
def sync_notifications(user_id):
    """即時通知：每10秒檢查是否有新跟團"""
    if user_id:
        try:
            res = supabase.table("groups").select("id, item_name").eq("creator_id", user_id).eq("has_new_join", True).execute()
            if res.data:
                for g in res.data:
                    st.toast(f"📢 有人加入你的「{g['item_name']}」分食團了！", icon="🎉")
        except: pass

user = get_user()

# --- 3. 側邊欄 UI ---
with st.sidebar:
    st.header("👤 會員選單")
    if user:
        sync_notifications(user.id) # 啟動即時通知
        my_nick = get_nickname(user.id)
        st.success(f"你好，{my_nick}")
        
        # 頁面切換
        page = st.radio("前往頁面", ["找分食/發起", "我的會員中心"])
        
        if st.button("登出系統"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        page = "找分食/發起"
        st.info("請先登入以使用完整功能")
        auth_mode = st.radio("登入/註冊", ["登入", "註冊"])
        email = st.text_input("Email")
        pw = st.text_input("密碼", type="password")
        if st.button("執行"):
            try:
                if auth_mode == "登入":
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
                    if res.user: 
                        st.session_state.user_obj = res.user
                        st.rerun()
                else:
                    res = supabase.auth.sign_up({"email": email, "password": pw})
                    if res.user:
                        supabase.table("profiles").insert({"id": res.user.id, "nickname": email.split('@')[0]}).execute()
                    st.info("註冊完成，請嘗試登入。")
            except Exception as e: st.error(f"錯誤: {e}")

# --- 4. 頁面邏輯：會員中心 ---
if user and page == "我的會員中心":
    st.title("🛡️ 會員中心")
    
    # 修改暱稱
    with st.expander("📝 修改個人資料"):
        new_nick = st.text_input("我的顯示暱稱", value=get_nickname(user.id))
        if st.button("更新暱稱"):
            supabase.table("profiles").upsert({"id": user.id, "nickname": new_nick}).execute()
            st.success("更新成功！")
            st.rerun()

    m1, m2, m3 = st.tabs(["📢 我的揪團", "🤝 我跟的團", "⌛ 歷史記錄"])
    
    with m1:
        my_groups = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "active").execute().data
        if not my_groups: st.write("目前沒有進行中的揪團。")
        for g in my_groups:
            with st.container(border=True):
                st.write(f"**{g['item_name']}**")
                st.write(f"剩餘份數：{g['remaining_units']} 份")
                if g['has_new_join']: st.warning("🆕 有新成員加入，確認後請手動已讀。")
                c1, c2 = st.columns(2)
                if c1.button("標記通知已讀", key=f"read_{g['id']}"):
                    supabase.table("groups").update({"has_new_join": False}).eq("id", g['id']).execute()
                    st.rerun()
                if c2.button("結案/刪除", key=f"close_{g['id']}"):
                    supabase.table("groups").update({"status": "closed", "has_new_join": False}).eq("id", g['id']).execute()
                    st.rerun()

    with m2:
        followed = supabase.table("group_members").select("*, groups(*)").eq("user_id", user.id).execute().data
        for f in followed:
            g = f['groups']
            if g and g['status'] == 'active':
                st.write(f"✅ 已加入 {g['creator_nickname']} 的「{g['item_name']}」")

    with m3:
        history = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "closed").execute().data
        for h in history:
            st.write(f"🌑 {h['item_name']} (於 {h['created_at'][:10]} 結束)")

# --- 5. 頁面邏輯：找分食/發起 ---
elif page == "找分食/發起":
    st.title("🛒 分食趣-現場媒合")
    tab1, tab2 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團"])

    with tab1:
        # 功能 1：手動更新按鈕
        col_title, col_refresh = st.columns([4, 1])
        col_title.subheader("現場待領清單")
        if col_refresh.button("🔄 刷新清單"):
            st.rerun()

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
                            # 顯示每份是多少數量
                            qty_per_unit = item['total_units'] // (item['remaining_units'] + item['self_units']) # 簡化計算
                            st.write(f"💵 價格：**${int(item['unit_price'])}** / 份")
                        with col_btn:
                            st.metric("剩餘", f"{item['remaining_units']} 份")
                            if st.button(f"我要 +1 份", key=f"join_{item['id']}"):
                                if not user: st.error("請先登入！")
                                elif user.id == item['creator_id']: st.warning("這是你發起的喔！")
                                else:
                                    new_remain = item['remaining_units'] - 1
                                    new_status = 'active' if new_remain > 0 else 'closed'
                                    # 更新並觸發通知
                                    supabase.table("groups").update({
                                        "remaining_units": new_remain, 
                                        "status": new_status,
                                        "has_new_join": True 
                                    }).eq("id", item['id']).execute()
                                    supabase.table("group_members").insert({"group_id": item['id'], "user_id": user.id}).execute()
                                    st.success(f"✅ 成功加入！已通知主揪。")
                                    st.balloons()
                                    st.rerun()
        except Exception as e: st.error(f"讀取失敗: {e}")

    with tab2:
        if not user:
            st.warning("🛑 發起揪團前請先登入。")
        else:
            if not st.session_state.confirm_publish:
                st.subheader("📢 設定揪團內容")
                
                # 店家與商品選單
                stores_res = supabase.table("stores").select("*").execute().data
                store_map = {s['branch_name']: s['id'] for s in stores_res}
                selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
                pops = supabase.table("popular_items").select("*").execute().data
                item_name = st.selectbox("商品名稱", [p['name'] for p in pops])
                
                # 功能 2：修改數量邏輯
                price = st.number_input("商品總價格", min_value=1, value=259)
                total_count = st.number_input("商品總個數 (如: 12顆)", min_value=1, value=12)
                
                st.divider()
                st.write("🔧 **分食單位設定**")
                col_a, col_b = st.columns(2)
                per_pack = col_a.number_input("幾顆為一份？", min_value=1, max_value=total_count, value=3)
                
                # 計算總份數
                total_parts = total_count // per_pack
                st.caption(f"💡 總共可分為 {total_parts} 份")
                
                my_stay_parts = col_b.number_input("主揪自留幾份？", min_value=1, max_value=total_parts, value=1)
                others_parts = total_parts - my_stay_parts
                
                st.metric("開放別人領取", f"{others_parts} 份")
                
                # 每份價格計算
                u_price = math.ceil(price / total_parts)
                st.info(f"💰 每份金額約為：${u_price} 元")

                if st.button("📝 檢查預覽", use_container_width=True):
                    st.session_state.temp_post = {
                        "item": item_name, "price": price, "u_price": u_price,
                        "others_parts": others_parts, "my_parts": my_stay_parts, 
                        "store_id": store_map[selected_store], "total_count": total_count
                    }
                    st.session_state.confirm_publish = True
                    st.rerun()
            else:
                p = st.session_state.temp_post
                st.subheader("📢 第二步：確認發布")
                st.warning(f"確認：{p['item']}\n總個數 {p['total_count']} 顆，分為 {p['my_parts'] + p['others_parts']} 份。\n您留 {p['my_parts']} 份，求分 {p['others_parts']} 份，每份 ${p['u_price']}。")
                
                c1, c2 = st.columns(2)
                if c1.button("❌ 修改內容"):
                    st.session_state.confirm_publish = False
                    st.rerun()
                if c2.button("✅ 正式發布", type="primary"):
                    new_data = {
                        "creator_id": user.id,
                        "creator_nickname": get_nickname(user.id),
                        "store_id": p['store_id'],
                        "item_name": p['item'],
                        "total_price": p['price'],
                        "total_units": p['total_count'], # 總顆數
                        "unit_price": p['u_price'],     # 每份單價
                        "remaining_units": p['others_parts'], # 改存份數
                        "self_units": p['my_parts'],      # 改存份數
                        "status": "active"
                    }
                    supabase.table("groups").insert(new_data).execute()
                    st.success("發布成功！")
                    st.balloons()
                    st.session_state.confirm_publish = False
                    st.rerun()