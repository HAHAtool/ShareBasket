import streamlit as st
from supabase import create_client
import math

# 1. 基礎連線
if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = st.session_state.supabase

if "confirm_publish" not in st.session_state: st.session_state.confirm_publish = False
if "temp_post" not in st.session_state: st.session_state.temp_post = None

# --- 2. 核心邏輯函數 ---

def get_user():
    if "user_obj" in st.session_state: return st.session_state.user_obj
    try:
        res = supabase.auth.get_session()
        if res and res.session:
            st.session_state.user_obj = res.user
            return res.user
    except: pass
    return None

def get_nickname(uid):
    try:
        res = supabase.table("profiles").select("nickname").eq("id", uid).maybe_single().execute()
        return res.data['nickname'] if res.data else "神秘分食友"
    except: return "未知用戶"

@st.fragment(run_every="10s")
def sync_notifications(user_id):
    """即時通知：僅限進行中的團"""
    if user_id:
        try:
            # 修改點 1：增加 status = 'active' 判斷，避免已結案的團一直跳通知
            res = supabase.table("groups").select("id, item_name")\
                .eq("creator_id", user_id)\
                .eq("has_new_join", True)\
                .eq("status", "active").execute()
            if res.data:
                for g in res.data:
                    st.toast(f"📢 有人加入你的「{g['item_name']}」分食團了！", icon="🎉")
        except: pass

user = get_user()

# --- 3. 側邊欄 UI ---
with st.sidebar:
    st.header("👤 會員選單")
    if user:
        sync_notifications(user.id)
        st.success(f"你好，{get_nickname(user.id)}")
        page = st.radio("前往頁面", ["找分食/發起", "我的會員中心"])
        if st.button("登出系統"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        page = "找分食/發起"
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
    with st.expander("📝 修改個人資料"):
        new_nick = st.text_input("我的顯示暱稱", value=get_nickname(user.id))
        if st.button("更新暱稱"):
            supabase.table("profiles").upsert({"id": user.id, "nickname": new_nick}).execute()
            st.success("更新成功！")
            st.rerun()

    m1, m2, m3 = st.tabs(["📢 我的揪團", "🤝 我跟的團", "⌛ 歷史記錄"])
    with m1:
        my_groups = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "active").execute().data
        if not my_groups: st.write("目前沒有進行中的發起。")
        else:
            for g in my_groups:
                with st.container(border=True):
                    st.write(f"**{g['item_name']}**")
                    st.write(f"剩餘份數：{g['remaining_units']} 份")
                    members = supabase.table("group_members").select("user_id").eq("group_id", g['id']).execute().data
                    if members:
                        st.write("👥 已跟團成員：")
                        for m in members: st.caption(f"- {get_nickname(m['user_id'])}")
                    if g['has_new_join']: st.warning("🆕 有新成員加入！")
                    c1, c2 = st.columns(2)
                    if c1.button("標記已讀", key=f"read_{g['id']}"):
                        supabase.table("groups").update({"has_new_join": False}).eq("id", g['id']).execute()
                        st.rerun()
                    if c2.button("結案/刪除", key=f"close_{g['id']}"):
                        supabase.table("groups").update({"status": "closed", "has_new_join": False}).eq("id", g['id']).execute()
                        st.rerun()
    with m2:
        followed_res = supabase.table("group_members").select("group_id, groups(*)").eq("user_id", user.id).execute()
        active_followed = [f for f in followed_res.data if f.get('groups') and f['groups']['status'] == 'active']
        if not active_followed: st.info("目前沒有參加中的揪團。")
        else:
            for f in active_followed:
                g = f['groups']
                with st.container(border=True):
                    st.write(f"✅ 已參加 **{g['creator_nickname']}** 的揪團")
                    st.subheader(g['item_name'])
                    st.write(f"💰 需支付：${int(g['unit_price'])}")
    with m3:
        history = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "closed").order("created_at", desc=True).execute().data
        for h in history: st.write(f"🌑 {h['item_name']} ({h['created_at'][:10]})")

# --- 5. 頁面邏輯：找分食/發起 ---
elif page == "找分食/發起":
    st.title("🛒 分食趣-現場媒合")
    tab1, tab2 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團"])

    with tab1:
        col_title, col_refresh = st.columns([4, 1])
        col_title.subheader("現場待領清單")
        if col_refresh.button("🔄 刷新清單"): st.rerun()
        try:
            res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").order("created_at", desc=True).execute()
            if not res.data: st.info("目前現場沒有人發起分食。")
            else:
                for item in res.data:
                    with st.container(border=True):
                        col_info, col_btn = st.columns([3, 1])
                        with col_info:
                            st.subheader(item['item_name'])
                            st.write(f"📍 {item['stores']['branch_name']} | 👤 主揪：{item['creator_nickname']}")
                            st.write(f"💵 價格：**${int(item['unit_price'])}** / 份")
                            if (item['total_price'] % (item['total_price'] // item['unit_price'])) != 0 if item['unit_price'] > 0 else False:
                                st.caption("⚠️ *註：此團總價除不盡，金額含進位雜費補貼*")
                        with col_btn:
                            st.metric("剩餘", f"{item['remaining_units']} 份")
                            if st.button(f"我要 +1 份", key=f"join_{item['id']}"):
                                if not user: st.error("請先登入！")
                                elif user.id == item['creator_id']: st.warning("這是你發起的喔！")
                                else:
                                    new_remain = item['remaining_units'] - 1
                                    new_status = 'active' if new_remain > 0 else 'closed'
                                    supabase.table("groups").update({"remaining_units": new_remain, "status": new_status, "has_new_join": True}).eq("id", item['id']).execute()
                                    supabase.table("group_members").insert({"group_id": item['id'], "user_id": user.id}).execute()
                                    st.success(f"✅ 成功加入！")
                                    st.rerun()
        except Exception as e: st.error(f"讀取失敗: {e}")

    with tab2:
        if not user: st.warning("🛑 發起揪團前請先登入。")
        else:
            if not st.session_state.confirm_publish:
                st.subheader("📢 設定揪團內容")
                stores_res = supabase.table("stores").select("*").execute().data
                store_map = {s['branch_name']: s['id'] for s in stores_res}
                selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
                pops = supabase.table("popular_items").select("*").execute().data
                item_name = st.selectbox("商品名稱", [p['name'] for p in pops])
                price = st.number_input("商品總價格", min_value=1, value=259)
                total_count = st.number_input("商品總個數", min_value=1, value=12)
                
                st.divider()
                st.write("🔧 **分食單位設定**")
                
                # 修改點 2：UI 排版調整
                col_a, col_b, col_c = st.columns(3)
                my_stay_count = col_a.number_input("主揪自留幾個？", min_value=1, max_value=total_count, value=2)
                
                # 顯示剩餘數量
                left_for_others = total_count - my_stay_count
                col_b.metric("剩下個數", f"{left_for_others} 個")
                
                per_pack = col_c.number_input("幾份為一個？", min_value=1, max_value=max(1, left_for_others), value=min(2, left_for_others))
                
                # 計算份數與金額
                others_parts = left_for_others // per_pack
                leftover_count = left_for_others % per_pack
                
                # 金額計算：無條件進位
                # 單價 = 總價 / (總份數) -> 總份數包含團員份數 + 主揪持有的份數(含餘數)比例
                u_price = math.ceil(price / (total_count / per_pack))
                
                # 主揪應付 = 總價 - (團員份數 * 單價)
                creator_pay = price - (others_parts * u_price)
                if creator_pay < 0: creator_pay = 0 # 避免單價太高導致主揪變負數 (雖然 ceil 不會發生)

                # 修改點 3：藍色與綠色結果跳出
                st.info(f"💡 結果：開放領取 **{others_parts}** 份，一份 **{per_pack}** 個。")
                if leftover_count > 0:
                    st.warning(f"⚠️ 無法整除的 **{leftover_count}** 個將歸入主揪自留 (主揪共得 {my_stay_count + leftover_count} 個)")
                
                st.success(f"💰 **預計主揪應付：${int(creator_pay)}** \n**剩餘分攤每份金額：${int(u_price)}** (採無條件進位)")

                if st.button("📝 檢查預覽", use_container_width=True):
                    st.session_state.temp_post = {
                        "item": item_name, "price": price, "u_price": u_price, "creator_pay": creator_pay,
                        "others_parts": others_parts, "my_total": my_stay_count + leftover_count, 
                        "store_id": store_map[selected_store], "total_count": total_count, "per_pack": per_pack
                    }
                    st.session_state.confirm_publish = True
                    st.rerun()
            else:
                p = st.session_state.temp_post
                st.subheader("📢 第二步：確認發布")
                st.warning(f"確認：{p['item']} (${p['price']})\n主揪領取：{p['my_total']} 個 (需付 ${int(p['creator_pay'])})\n團員領取：{p['others_parts']} 份 (每份 ${int(p['u_price'])})")
                c1, c2 = st.columns(2)
                if c1.button("❌ 修改內容"):
                    st.session_state.confirm_publish = False
                    st.rerun()
                if c2.button("✅ 正式發布", type="primary"):
                    supabase.table("groups").insert({
                        "creator_id": user.id, "creator_nickname": get_nickname(user.id),
                        "store_id": p['store_id'], "item_name": p['item'], "total_price": p['price'],
                        "total_units": p['total_count'], "unit_price": p['u_price'],     
                        "remaining_units": p['others_parts'], "self_units": 1, "status": "active"
                    }).execute()
                    st.success("發布成功！")
                    st.session_state.confirm_publish = False
                    st.rerun()