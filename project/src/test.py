import streamlit as st

# 1. Top Area
with st.container(border=True):
    st.subheader("🔼 Top Area")
    st.write("This is your header or navigation section.")
    st.text_input("Search something...", key="top_search")

# 2. Middle Area
with st.container(border=True):
    st.subheader("↔️ Middle Area")
    st.write("This is your main content area.")
    # You can even put columns INSIDE a row container
    left, right = st.columns(2)
    left.metric("Sales", "$12,000", "+5%")
    right.metric("Users", "1,240", "+12%")

# 3. Bottom Area
with st.container(border=True):
    st.subheader("🔽 Bottom Area")
    st.write("This is your footer or action item section.")
    if st.button("Submit All Data", type="primary"):
        st.success("Data submitted!")