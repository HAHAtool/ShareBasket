import streamlit as st
from supabase import create_client
import math
from datetime import datetime

# 1. 基礎連線與初始化
if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = st.session_state.supabase

# 狀態管理
if "confirm_publish" not in st.session_state: st.session_state.confirm_publish = False
if "temp_post" not in st.session_state: st.session_state.temp_post = None
if "active_chat_id" not in st.session_state: st.session_state.active_chat_id = None

# --- 2. 核心邏輯函數 ---

def get_user():
    """強化版：雙重檢查 Session"""
    if "user_obj" in st.session_state: return st.session_state.user_obj
    try:
        res = supabase.auth.get_session()
        if res and res.session:
            st.session_state.user_obj = res.user
            return res.user
    except: pass
    return None

def get_nickname(uid):
    """取得暱稱，若無則回傳預設"""
    try:
        res = supabase.table("profiles").select("nickname").eq("id", uid).maybe_single().execute()
        return res.data['nickname'] if res.data else "神秘分食友"
    except: return "未知用戶"

@st.fragment(run_every="10s")
def sync_notifications(user_id):
    """即時通知：僅偵測進行中的團"""
    if user_id:
        try:
            res = supabase.table("groups").select("id, item_name").eq("creator_id", user_id).eq("has_new_join", True).eq("status", "active").execute()
            if res.data:
                for g in res.data:
                    st.toast(f"🔔 有人加入你的「{g['item_name']}」團了！", icon="🎉")
        except: pass

@st.fragment(run_every="5s")
def render_chat(group_id, current_user_id):
    """內建聊天室 Fragment：每 5 秒更新一次"""
    st.markdown("---")
    st.subheader("💬 團內討論區 (匿名)")
    
    # 抓取訊息
    msgs = supabase.table("messages").select("*").eq("group_id", group_id).order("created_at", desc=False).execute().data
    
    # 顯示對話樣式
    chat_container = st.container(height=300)
    with chat_container:
        if not msgs:
            st.caption("目前尚無對話，打個招呼吧！")
        for m in msgs:
            is_me = str(m['user_id']) == str(current_user_id)
            with st.chat_message("user" if is_me else "assistant"):
                st.write(f"**{m['user_nickname']}**: {m['content']}")
                st.caption(f"{m['created_at'][11:16]}")

    # 輸入框 (在 Fragment 內，發送不會重整全網頁)
    if prompt := st.chat_input("輸入訊息..."):
        my_nick = get_nickname(current_user_id)
        supabase.table("messages").insert({
            "group_id": group_id,
            "user_id": current_user_id,
            "user_nickname": my_nick,
            "content": prompt
        }).execute()
        st.rerun()

user = get_user()

# --- 3. 側邊欄 UI ---
with st.sidebar:
    st.header("👤 會員選單")
    if user:
        sync_notifications(user.id)
        st.success(f"你好，{get_nickname(user.id)}")
        page = st.radio("前往頁面", ["🔍 找分食清單", "📢 我要發起揪團", "🛡️ 會員控制台"])
        if st.button("登出系統"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        page = "🔍 找分食清單"
        auth_mode = st.radio("登入/註冊", ["登入", "註冊"])
        email = st.text_input("Email")
        pw = st.text_input("密碼", type="password")
        if st.button("確認"):
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

# --- 4. 頁面邏輯：會員中心 (生命週期管理核心) ---
if page == "🛡️ 會員控制台" and user:
    st.title("🛡️ 會員中心")
    
    with st.expander("📝 修改暱稱"):
        new_nick = st.text_input("新暱稱", value=get_nickname(user.id))
        if st.button("儲存"):
            supabase.table("profiles").upsert({"id": user.id, "nickname": new_nick}).execute()
            st.success("暱稱已更新！")
            st.rerun()

    m1, m2, m3 = st.tabs(["📢 我發起的", "🤝 我參加的", "⌛ 歷史記錄"])
    
    with m1:
        my_groups = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "active").execute().data
        if not my_groups: st.info("尚無進行中的發起。")
        for g in my_groups:
            with st.container(border=True):
                st.subheader(g['item_name'])
                status_text = "🟢 開放中" if g['remaining_units'] > 0 else "🟠 已額滿 (待面交)"
                st.write(f"狀態：{status_text} | 剩餘：{g['remaining_units']} 份")
                
                c1, c2, c3 = st.columns(3)
                if c1.button("標記已讀", key=f"r_{g['id']}"):
                    supabase.table("groups").update({"has_new_join": False}).eq("id", g['id']).execute()
                    st.rerun()
                if c2.button("進入聊天室", key=f"chat_h_{g['id']}"):
                    st.session_state.active_chat_id = g['id']
                if c3.button("✅ 面交完成/結案", key=f"close_{g['id']}", type="primary"):
                    supabase.table("groups").update({"status": "closed", "has_new_join": False}).eq("id", g['id']).execute()
                    st.session_state.active_chat_id = None
                    st.rerun()
                
                if st.session_state.active_chat_id == g['id']:
                    render_chat(g['id'], user.id)

    with m2:
        followed_res = supabase.table("group_members").select("group_id, groups(*)").eq("user_id", user.id).execute()
        # 過濾出 status != 'closed' 的參加項目
        active_follows = [f for f in followed_res.data if f.get('groups') and f['groups']['status'] == 'active']
        if not active_follows: st.info("尚無參加中的揪團。")
        for f in active_follows:
            g = f['groups']
            with st.container(border=True):
                st.subheader(g['item_name'])
                st.write(f"主揪：{g['creator_nickname']} | 需支付：${int(g['unit_price'])}")
                if st.button("進入聊天室", key=f"chat_j_{g['id']}"):
                    st.session_state.active_chat_id = g['id']
                if st.session_state.active_chat_id == g['id']:
                    render_chat(g['id'], user.id)

    with m3:
        history = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "closed").order("created_at", desc=True).execute().data
        for h in history: st.write(f"🌑 {h['item_name']} (結案時間：{h['created_at'][:10]})")

# --- 5. 頁面邏輯：找分食/發起 ---
elif page == "🔍 找分食清單":
    st.title("🔍 找分食清單")
    if st.button("🔄 刷新頁面清單"): st.rerun()
    
    try:
        res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").order("created_at", desc=True).execute()
        for item in res.data:
            with st.container(border=True):
                col_info, col_btn = st.columns([3, 1])
                with col_info:
                    st.subheader(item['item_name'])
                    st.write(f"📍 {item['stores']['branch_name']} | 👤 主揪：{item['creator_nickname']}")
                    st.write(f"💵 價格：**${int(item['unit_price'])}** / 份")
                with col_btn:
                    if item['remaining_units'] > 0:
                        st.metric("剩餘", f"{item['remaining_units']} 份")
                        if st.button(f"我要 +1", key=f"join_{item['id']}"):
                            if not user: st.error("請先登入！")
                            elif user.id == item['creator_id']: st.warning("這是你發起的。")
                            else:
                                new_remain = item['remaining_units'] - 1
                                # 注意：這裡不再自動改為 closed，保持 active 供聊天
                                supabase.table("groups").update({"remaining_units": new_remain, "has_new_join": True}).eq("id", item['id']).execute()
                                supabase.table("group_members").insert({"group_id": item['id'], "user_id": user.id}).execute()
                                st.success("✅ 成功加入！請至『會員中心』與主揪聯繫。")
                                st.rerun()
                    else:
                        st.warning("🟠 已額滿")
                        st.caption("面交進行中")
    except Exception as e: st.error(f"錯誤: {e}")

elif page == "📢 我要發起揪團":
    if not user:
        st.warning("🛑 請先登入帳號。")
    else:
        if not st.session_state.confirm_publish:
            st.title("📢 發起分食揪團")
            stores_res = supabase.table("stores").select("*").execute().data
            store_map = {s['branch_name']: s['id'] for s in stores_res}
            selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
            pops = supabase.table("popular_items").select("*").execute().data
            item_name = st.selectbox("商品名稱", [p['name'] for p in pops])
            price = st.number_input("商品總價格", min_value=1, value=259)
            total_count = st.number_input("商品總個數", min_value=1, value=12)
            
            st.divider()
            col_a, col_b, col_c = st.columns(3)
            my_stay = col_a.number_input("主揪自留幾個？", min_value=1, max_value=total_count, value=2)
            left_for_others = total_count - my_stay
            col_b.metric("剩下個數", f"{left_for_others} 個")
            per_pack = col_c.number_input("幾份為一個？", min_value=1, max_value=max(1, left_for_others), value=min(2, left_for_others))
            
            others_parts = left_for_others // per_pack
            leftover = left_for_others % per_pack
            u_price = math.ceil(price / (total_count / per_pack))
            creator_pay = price - (others_parts * u_price)

            st.info(f"💡 開放領取 **{others_parts}** 份，一份 **{per_pack}** 個。")
            if leftover > 0: st.warning(f"⚠️ 餘數 {leftover} 顆歸主揪 (共 {my_stay + leftover} 顆)")
            st.success(f"💰 主揪應付：${int(creator_pay)} | 團員每份：${int(u_price)}")

            if st.button("📝 檢查預覽", use_container_width=True):
                st.session_state.temp_post = {
                    "item": item_name, "price": price, "u_price": u_price, "creator_pay": creator_pay,
                    "others_parts": others_parts, "my_total": my_stay + leftover, 
                    "store_id": store_map[selected_store], "total_count": total_count, "per_pack": per_pack
                }
                st.session_state.confirm_publish = True
                st.rerun()
        else:
            p = st.session_state.temp_post
            st.subheader("📢 確認發布")
            st.warning(f"確認：{p['item']} (${p['price']})\n主揪領：{p['my_total']} 個 (付 ${int(p['creator_pay'])})\n團員領：{p['others_parts']} 份 (每份 ${int(p['u_price'])})")
            c1, c2 = st.columns(2)
            if c1.button("❌ 修改"): st.session_state.confirm_publish = False; st.rerun()
            if c2.button("✅ 正式發布", type="primary"):
                supabase.table("groups").insert({
                    "creator_id": user.id, "creator_nickname": get_nickname(user.id),
                    "store_id": p['store_id'], "item_name": p['item'], "total_price": p['price'],
                    "total_units": p['total_count'], "unit_price": p['u_price'],     
                    "remaining_units": p['others_parts'], "self_units": 1, "status": "active"
                }).execute()
                st.success("成功！請至控制台與團員溝通。")
                st.session_state.confirm_publish = False
                st.rerun()