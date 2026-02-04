import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv

# 1. 載入金鑰 (本地開發用 .env, 部署後用 Streamlit Secrets)
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

st.set_page_config(page_title="好市多分食趣", page_icon="🛒")

# 介面標題
st.title("🛒 好市多分食現場媒合")

# 分成兩個頁籤
tab1, tab2 = st.tabs(["🔍 我要分食 (找清單)", "📢 我要發起 (現場揪)"])

# --- Tab 1: 找清單 ---
with tab1:
    res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").execute()
    items = res.data

    if not items:
        st.info("目前還沒人在揪喔！")
    else:
        for item in items:
            with st.container(border=True):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.subheader(item['item_name'])
                    st.write(f"📍 {item['stores']['branch_name']} | 單價: ${int(item['unit_price'])}")
                with c2:
                    st.metric("剩餘", item['remaining_units'])
                    if st.button(f"我要 +1", key=item['id']):
                        new_remain = item['remaining_units'] - 1
                        status = 'active' if new_remain > 0 else 'closed'
                        supabase.table("groups").update({"remaining_units": new_remain, "status": status}).eq("id", item['id']).execute()
                        st.success("已成功預約！請在現場尋找發起人。")
                        st.rerun()

# --- Tab 2: 發起揪團 ---
with tab2:
    st.write("請填寫以下資訊，免打字，點選即可：")
    name = st.text_input("你的暱稱", value="阿肥")
    
    # 商店選單
    stores_res = supabase.table("stores").select("*").execute()
    store_options = {s['branch_name']: s['id'] for s in stores_res.data}
    sel_store = st.selectbox("在哪間分店？", list(store_options.keys()))

    # 熱門商品按鈕
    pop_res = supabase.table("popular_items").select("*").execute()
    pop_names = [i['name'] for i in pop_res.data]
    sel_item = st.pills("選擇商品", pop_names)

    if sel_item:
        price = st.number_input("總價格", min_value=0, value=259)
        units = st.number_input("總入數", min_value=1, value=12)
        u_price = math.ceil(price / units)
        st.write(f"💰 計算單價為: **${u_price}**")

        if st.button("🚀 確認發布", use_container_width=True):
            supabase.table("groups").insert({
                "creator_nickname": name,
                "store_id": store_options[sel_store],
                "item_name": sel_item,
                "total_price": price,
                "total_units": units,
                "unit_price": u_price,
                "remaining_units": units
            }).execute()
            st.success("發布成功！")
            st.balloons()