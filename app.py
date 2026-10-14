import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ----------------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Funnel Analysis Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

FUNNEL_STAGES = ['Browse', 'Add to Cart', 'Checkout', 'Purchase']

# ----------------------------------------------------------------------------
# DATA LOADING & PROCESSING (cached so it only re-runs when the file changes)
# ----------------------------------------------------------------------------
@st.cache_data
def load_data(file):
    df = pd.read_csv(file)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df['Date'] = df['Timestamp'].dt.date
    df['DayOfWeek'] = df['Timestamp'].dt.day_name()
    df['Hour'] = df['Timestamp'].dt.hour
    return df


@st.cache_data
def build_session_summary(df):
    session_summary = df.groupby('Session_ID').agg({
        'User_ID': 'first',
        'Timestamp': ['min', 'max'],
        'Event': lambda x: list(x),
        'Device': 'first',
        'Region': 'first',
        'Channel': 'first',
        'Product_Category': 'first',
        'Revenue': 'max',
        'Bounce_Flag': 'first'
    }).reset_index()

    session_summary.columns = ['Session_ID', 'User_ID', 'Session_Start', 'Session_End',
                                'Event_Sequence', 'Device', 'Region', 'Channel',
                                'Product_Category', 'Revenue', 'Bounce_Flag']

    session_summary['Session_Duration_Min'] = (
        session_summary['Session_End'] - session_summary['Session_Start']
    ).dt.total_seconds() / 60

    def get_max_funnel_stage(events):
        stage_values = {stage: i for i, stage in enumerate(FUNNEL_STAGES)}
        max_stage_index = -1
        for event in events:
            if event in stage_values and stage_values[event] > max_stage_index:
                max_stage_index = stage_values[event]
        return FUNNEL_STAGES[max_stage_index] if max_stage_index != -1 else 'Browse'

    session_summary['Max_Funnel_Stage'] = session_summary['Event_Sequence'].apply(get_max_funnel_stage)
    return session_summary


def build_funnel_df(session_summary):
    funnel_metrics = []
    for i, stage in enumerate(FUNNEL_STAGES):
        if i == 0:
            count = len(session_summary)
        else:
            count = len(session_summary[session_summary['Max_Funnel_Stage'].isin(FUNNEL_STAGES[i:])])
        funnel_metrics.append({'Stage': stage, 'Sessions': count, 'Stage_Order': i})

    funnel_df = pd.DataFrame(funnel_metrics)
    if funnel_df['Sessions'].iloc[0] > 0:
        funnel_df['Conversion_Rate'] = (funnel_df['Sessions'] / funnel_df['Sessions'].iloc[0] * 100).round(2)
    else:
        funnel_df['Conversion_Rate'] = 0
    funnel_df['Drop_Off_Rate'] = (1 - funnel_df['Sessions'] / funnel_df['Sessions'].shift(1)) * 100
    funnel_df.loc[0, 'Drop_Off_Rate'] = 0
    funnel_df['Drop_Off_Rate'] = funnel_df['Drop_Off_Rate'].round(2)
    return funnel_df


def build_segment_analysis(session_summary, segment_col):
    seg = session_summary.groupby(segment_col).agg({
        'Session_ID': 'count',
        'Revenue': 'sum',
        'Session_Duration_Min': 'mean',
        'Max_Funnel_Stage': lambda x: (x == 'Purchase').sum()
    }).rename(columns={'Session_ID': 'Total_Sessions', 'Max_Funnel_Stage': 'Purchases'})

    seg['Conversion_Rate'] = (seg['Purchases'] / seg['Total_Sessions'] * 100).round(2)
    seg['AOV'] = (seg['Revenue'] / seg['Purchases']).round(2)
    seg['Revenue_Per_Session'] = (seg['Revenue'] / seg['Total_Sessions']).round(2)
    return seg.reset_index()


# ----------------------------------------------------------------------------
# SIDEBAR: DATA SOURCE + FILTERS
# ----------------------------------------------------------------------------
st.sidebar.title("⚙️ Controls")
default_path = "funnel_analysis_data.csv"


try:
    raw_df = load_data(default_path)
except FileNotFoundError:
    st.sidebar.warning("Please upload a CSV file to get started.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")

min_date, max_date = raw_df['Date'].min(), raw_df['Date'].max()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date),
                                    min_value=min_date, max_value=max_date)

channels = st.sidebar.multiselect("Channel", sorted(raw_df['Channel'].unique()),
                                   default=sorted(raw_df['Channel'].unique()))
regions = st.sidebar.multiselect("Region", sorted(raw_df['Region'].unique()),
                                  default=sorted(raw_df['Region'].unique()))
devices = st.sidebar.multiselect("Device", sorted(raw_df['Device'].unique()),
                                  default=sorted(raw_df['Device'].unique()))
categories = st.sidebar.multiselect("Product Category", sorted(raw_df['Product_Category'].unique()),
                                     default=sorted(raw_df['Product_Category'].unique()))

# Apply filters
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

df = raw_df[
    (raw_df['Date'] >= start_date) & (raw_df['Date'] <= end_date) &
    (raw_df['Channel'].isin(channels)) &
    (raw_df['Region'].isin(regions)) &
    (raw_df['Device'].isin(devices)) &
    (raw_df['Product_Category'].isin(categories))
].copy()

if df.empty:
    st.warning("No data matches the selected filters. Adjust filters in the sidebar.")
    st.stop()

session_summary = build_session_summary(df)
funnel_df = build_funnel_df(session_summary)

# ----------------------------------------------------------------------------
# HEADER + KPIs
# ----------------------------------------------------------------------------
st.title("📊 E-Commerce Funnel Analysis Dashboard")
st.caption("Browse → Add to Cart → Checkout → Purchase")

total_sessions = len(session_summary)
total_revenue = session_summary['Revenue'].sum()
total_orders = len(session_summary[session_summary['Max_Funnel_Stage'] == 'Purchase'])
overall_conv_rate = (total_orders / total_sessions * 100) if total_sessions else 0
aov = (total_revenue / total_orders) if total_orders else 0
bounce_rate = (len(session_summary[session_summary['Bounce_Flag'] == 'Yes']) / total_sessions * 100) if total_sessions else 0

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Sessions", f"{total_sessions:,}")
k2.metric("Total Orders", f"{total_orders:,}")
k3.metric("Overall Conversion", f"{overall_conv_rate:.2f}%")
k4.metric("Total Revenue", f"${total_revenue:,.0f}")
k5.metric("Avg Order Value", f"${aov:,.2f}")
k6.metric("Bounce Rate", f"{bounce_rate:.2f}%")

st.markdown("---")

# ----------------------------------------------------------------------------
# TABS
# ----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🔻 Overall Funnel", "📣 Channel", "🌍 Region",
    "📱 Device & Category", "🕒 Time Trends", "💡 Recommendations"
])

# --- TAB 1: OVERALL FUNNEL ---
with tab1:
    col1, col2 = st.columns(2)

    with col1:
        fig_funnel = go.Figure(go.Funnel(
            y=funnel_df['Stage'],
            x=funnel_df['Sessions'],
            textinfo="value+percent initial"
        ))
        fig_funnel.update_layout(title="Funnel: Sessions by Stage")
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col2:
        fig_drop = px.line(funnel_df, x='Stage', y='Drop_Off_Rate', markers=True,
                            title="Stage-to-Stage Drop-off Rate (%)")
        fig_drop.update_traces(line_color='red')
        st.plotly_chart(fig_drop, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        revenue_by_stage = session_summary.groupby('Max_Funnel_Stage')['Revenue'].sum().reindex(FUNNEL_STAGES).reset_index()
        fig_rev = px.bar(revenue_by_stage, x='Max_Funnel_Stage', y='Revenue',
                          title="Revenue by Max Funnel Stage Reached", color_discrete_sequence=['green'])
        st.plotly_chart(fig_rev, use_container_width=True)

    with col4:
        duration_by_stage = session_summary.groupby('Max_Funnel_Stage')['Session_Duration_Min'].mean().reindex(FUNNEL_STAGES).reset_index()
        fig_dur = px.bar(duration_by_stage, x='Max_Funnel_Stage', y='Session_Duration_Min',
                          title="Avg Session Duration by Stage (min)", color_discrete_sequence=['orange'])
        st.plotly_chart(fig_dur, use_container_width=True)

    st.subheader("Funnel Table")
    st.dataframe(funnel_df, use_container_width=True)

# --- TAB 2: CHANNEL ---
with tab2:
    channel_df = build_segment_analysis(session_summary, 'Channel')
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(channel_df, x='Channel', y='Conversion_Rate', color='Channel',
                      title="Conversion Rate by Channel", text_auto='.2f')
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(channel_df, x='Channel', y='Revenue', color='Channel',
                      title="Total Revenue by Channel", text_auto='.2s')
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        fig = px.bar(channel_df, x='Channel', y='AOV', color='Channel', title="AOV by Channel")
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        fig = px.pie(channel_df, names='Channel', values='Total_Sessions', title="Session Share by Channel")
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(channel_df, use_container_width=True)

# --- TAB 3: REGION ---
with tab3:
    regional_df = build_segment_analysis(session_summary, 'Region')

    region_funnel_data = []
    for region in session_summary['Region'].unique():
        region_sessions = session_summary[session_summary['Region'] == region]
        for i, stage in enumerate(FUNNEL_STAGES):
            count = len(region_sessions) if i == 0 else len(
                region_sessions[region_sessions['Max_Funnel_Stage'].isin(FUNNEL_STAGES[i:])])
            region_funnel_data.append({'Region': region, 'Stage': stage, 'Sessions': count})
    region_funnel_df = pd.DataFrame(region_funnel_data)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.line(region_funnel_df, x='Stage', y='Sessions', color='Region', markers=True,
                      title="Funnel Progression by Region")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(regional_df, x='Region', y='Conversion_Rate', color='Region',
                      title="Conversion Rate by Region")
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(regional_df, use_container_width=True)

# --- TAB 4: DEVICE & CATEGORY ---
with tab4:
    device_df = build_segment_analysis(session_summary, 'Device')
    product_df = build_segment_analysis(session_summary, 'Product_Category')

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(device_df, x='Device', y='Conversion_Rate', color='Device',
                      title="Conversion Rate by Device")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(product_df, x='Product_Category', y='Conversion_Rate', color='Product_Category',
                      title="Conversion Rate by Product Category")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Device Performance")
    st.dataframe(device_df, use_container_width=True)
    st.subheader("Product Category Performance")
    st.dataframe(product_df, use_container_width=True)

# --- TAB 5: TIME TRENDS ---
with tab5:
    daily_metrics = df.groupby('Date').agg({
        'Session_ID': 'nunique',
        'User_ID': 'nunique',
        'Revenue': 'sum'
    }).rename(columns={'Session_ID': 'Daily_Sessions', 'User_ID': 'Daily_Users'})

    daily_conversions = session_summary[session_summary['Max_Funnel_Stage'] == 'Purchase'].copy()
    daily_conversions['Date'] = daily_conversions['Session_Start'].dt.date
    daily_conv_counts = daily_conversions.groupby('Date').size()
    daily_metrics['Daily_Conversions'] = daily_conv_counts
    daily_metrics['Daily_Conversions'] = daily_metrics['Daily_Conversions'].fillna(0)
    daily_metrics['Daily_Conversion_Rate'] = (daily_metrics['Daily_Conversions'] / daily_metrics['Daily_Sessions'] * 100).round(2)
    daily_metrics = daily_metrics.reset_index()

    hourly_sessions = df.groupby('Hour').agg({
        'Session_ID': 'nunique',
        'Revenue': 'sum'
    }).rename(columns={'Session_ID': 'Hourly_Sessions'})

    hourly_conversions = session_summary[session_summary['Max_Funnel_Stage'] == 'Purchase'].copy()
    hourly_conversions['Hour'] = hourly_conversions['Session_Start'].dt.hour
    hourly_conv_counts = hourly_conversions.groupby('Hour').size()
    hourly_sessions['Hourly_Conversions'] = hourly_conv_counts
    hourly_sessions['Hourly_Conversions'] = hourly_sessions['Hourly_Conversions'].fillna(0)
    hourly_sessions['Hourly_Conversion_Rate'] = (hourly_sessions['Hourly_Conversions'] / hourly_sessions['Hourly_Sessions'] * 100).round(2)
    hourly_sessions = hourly_sessions.reset_index()

    c1, c2 = st.columns(2)
    with c1:
        fig = px.line(daily_metrics, x='Date', y='Daily_Sessions', title="Daily Sessions Over Time")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.line(daily_metrics, x='Date', y='Daily_Conversion_Rate', title="Daily Conversion Rate (%)")
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        fig = px.bar(hourly_sessions, x='Hour', y='Hourly_Sessions', title="Sessions by Hour of Day")
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        fig = px.bar(hourly_sessions, x='Hour', y='Hourly_Conversion_Rate', title="Conversion Rate by Hour of Day")
        st.plotly_chart(fig, use_container_width=True)

# --- TAB 6: RECOMMENDATIONS ---
with tab6:
    st.subheader("🎯 Key Performance Indicators")
    st.write(f"- **Overall Conversion Rate:** {overall_conv_rate:.2f}%")
    st.write(f"- **Total Revenue:** ${total_revenue:,.2f}")
    st.write(f"- **Average Order Value:** ${aov:,.2f}")
    st.write(f"- **Bounce Rate:** {bounce_rate:.2f}%")

    if len(funnel_df) > 1 and funnel_df['Drop_Off_Rate'].iloc[1:].notna().any():
        max_dropoff = funnel_df.loc[funnel_df['Drop_Off_Rate'].iloc[1:].idxmax()]
        st.warning(f"⚠️ **Biggest drop-off:** {max_dropoff['Stage']} stage, {max_dropoff['Drop_Off_Rate']:.2f}% of users leave here.")

    channel_df = build_segment_analysis(session_summary, 'Channel')
    regional_df = build_segment_analysis(session_summary, 'Region')
    product_df = build_segment_analysis(session_summary, 'Product_Category')

    if not channel_df.empty:
        best_channel = channel_df.loc[channel_df['Conversion_Rate'].idxmax()]
        st.success(f"🏆 **Best channel:** {best_channel['Channel']} — {best_channel['Conversion_Rate']:.2f}% conversion")
    if not regional_df.empty:
        best_region = regional_df.loc[regional_df['Conversion_Rate'].idxmax()]
        st.success(f"🌍 **Best region:** {best_region['Region']} — {best_region['Conversion_Rate']:.2f}% conversion")
    if not product_df.empty:
        best_category = product_df.loc[product_df['Conversion_Rate'].idxmax()]
        st.success(f"🛍️ **Best category:** {best_category['Product_Category']} — {best_category['Conversion_Rate']:.2f}% conversion")

    st.subheader("📋 Recommended Actions")
    st.markdown("""
    1. **Fix the biggest drop-off stage** — investigate UX/friction at that step (form length, load time, trust signals).
    2. **Reallocate budget** toward the best-performing channel.
    3. **Study and replicate** the top region's strategy in underperforming regions.
    4. **Promote the top-converting product category** more prominently.
    5. **Target cart/checkout abandonment** with reminder emails or retargeting ads.
    """)

    st.subheader("📥 Export")
    export_data = {
        'Overall_Funnel': funnel_df,
        'Channel_Performance': channel_df,
        'Regional_Analysis': regional_df,
        'Device_Performance': build_segment_analysis(session_summary, 'Device'),
        'Product_Performance': product_df,
    }
    import io
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        for sheet_name, data in export_data.items():
            data.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    buffer.seek(0)

    st.download_button(
        label="Download Full Report (Excel)",
        data=buffer,
        file_name="funnel_analysis_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.markdown("---")
st.caption("Built with Streamlit • Filters apply across all tabs")
