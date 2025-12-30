import PyUber
import pandas as pd
import numpy as np
import dash
from dash import Dash, dcc, html, State, callback
from dash import dash_table as dt
from dash.dependencies import Input, Output
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from datetime import timedelta
import numpy as np

SQL_DATA = '''
SELECT 
          a2.monitor_set_name AS monitor_set_name
         ,a5.value AS chart_value
         ,a5.test_name AS chart_test_name
         ,a0.operation AS spc_operation
         ,a1.entity AS entity
         ,To_Char(a1.data_collection_time,'yyyy-mm-dd hh24:mi:ss') AS entity_data_collect_date
         ,a10.centerline AS centerline
         ,a10.lo_control_lmt AS lo_control_lmt
         ,a10.up_control_lmt AS up_control_lmt
         ,CASE WHEN a10.centerline IS NULL THEN -99 WHEN a5.value BETWEEN a10.centerline - ((a10.centerline - a10.lo_control_lmt)/3) AND a10.centerline Then -1 WHEN a5.value BETWEEN a10.centerline AND a10.centerline + ((a10.up_control_lmt - a10.centerline)/3) THEN 1 WHEN a5.value BETWEEN a10.centerline - (2*((a10.centerline - a10.lo_control_lmt)/3)) AND a10.centerline THEN -2 WHEN a5.value BETWEEN a10.centerline AND a10.centerline + (2*((a10.up_control_lmt - a10.centerline)/3)) THEN 2 WHEN a5.value Between a10.lo_control_lmt AND a10.centerline - (2.*((a10.centerline - a10.lo_control_lmt)/3.)) THEN -3 WHEN a5.value Between a10.centerline + (2*((a10.up_control_lmt - a10.centerline)/3)) AND a10.up_control_lmt THEN 3 WHEN a5.value > a10.up_control_lmt THEN 4 WHEN a5.value < a10.lo_control_lmt THEN -4 ELSE 999 END AS zone
         ,a5.spc_chart_category AS spc_chart_category
         ,a5.spc_chart_subset AS spc_chart_subset
         ,a0.lot AS lot
         ,To_Char(a0.data_collection_time,'yyyy-mm-dd hh24:mi:ss') AS lot_data_collect_date
         ,a0.route AS route
         ,a3.parameter_class AS parameter_class
         ,a3.measurement_set_name AS measurement_set_name
         ,a2.violation_flag AS violation_flag
         ,a5.valid_flag AS chart_pt_valid_flag
         ,a5.standard_flag AS chart_standard_flag
         ,a5.chart_type AS chart_type
         ,a4.foup_slot AS foup_slot
         ,a4.wafer AS raw_wafer
         ,a4.value AS raw_value
         ,a4.wafer3 AS raw_wafer3
FROM 
P_SPC_ENTITY a1
LEFT JOIN P_SPC_Lot a0 ON a0.spcs_id = a1.spcs_id
INNER JOIN P_SPC_SESSION a2 ON a2.spcs_id = a1.spcs_id AND a2.data_collection_time=a1.data_collection_time
INNER JOIN P_SPC_MEASUREMENT_SET a3 ON a3.spcs_id = a2.spcs_id
INNER JOIN P_SPC_CHART_POINT a5 ON a5.spcs_id = a3.spcs_id AND a5.measurement_set_name = a3.measurement_set_name
LEFT JOIN P_SPC_CHARTPOINT_MEASUREMENT a7 ON a7.spcs_id = a3.spcs_id and a7.measurement_set_name = a3.measurement_set_name
AND a5.spcs_id = a7.spcs_id AND a5.chart_id = a7.chart_id AND a5.chart_point_seq = a7.chart_point_seq AND a5.measurement_set_name = a7.measurement_set_name
LEFT JOIN P_SPC_CHART_LIMIT a10 ON a10.chart_id = a5.chart_id AND a10.limit_id = a5.limit_id
LEFT JOIN P_SPC_MEASUREMENT a4 ON a4.spcs_id = a3.spcs_id AND a4.measurement_set_name = a3.measurement_set_name
AND a4.spcs_id = a7.spcs_id AND a4.measurement_id = a7.measurement_id
WHERE
 (a2.monitor_set_name Like '%DSA_PST_NONPAT.5051.MON' or a2.monitor_set_name Like '%DSA_PST.5051.MON')
 AND      a0.operation In ('8281','8333') 
 AND      (a1.entity Like 'TBC611%' or a1.entity Like 'TZH591%')
 AND      a1.data_collection_time >= SYSDATE - 210
'''


try:
    conn = PyUber.connect(datasource='F21_PROD_XEUS')
    df = pd.read_sql(SQL_DATA, conn)
except:
    print('Cannot run SQL script - Consider connecting to VPN')

# Extract the RESIST value and create a new column
df['RESIST'] = df['SPC_CHART_CATEGORY'].str.extract(r'RESIST=([^;]+)')
# Remove the 'PARTICLE_SIZE=' portion from the 'SPC_CHART_SUBSET' column values
df['SPC_CHART_SUBSET'] = df['SPC_CHART_SUBSET'].str.replace('PARTICLE_SIZE=', '')

# Rename columns
df.rename(columns={'VIOLATION_FLAG': 'FAIL', 'CHART_PT_VALID_FLAG': 'VALID_FLAG', 'CHART_STANDARD_FLAG': 'STD_FLAG'}, inplace=True)
# Create the VALID column based on VALID_FLAG and STD_FLAG
df['VALID'] = df.apply(lambda row: 'N' if row['VALID_FLAG'] == 'N' or row['STD_FLAG'] == 'N' else 'Y', axis=1)

# Adjust ENTITY_DATA_COLLECT_DATE for each group of unique ENTITY, ENTITY_DATA_COLLECT_DATE, RAW_WAFER
df['ENTITY_DATA_COLLECT_DATE'] = pd.to_datetime(df['ENTITY_DATA_COLLECT_DATE'])  # Ensure the column is in datetime format
df = df.sort_values(by=['ENTITY', 'ENTITY_DATA_COLLECT_DATE', 'FOUP_SLOT'])  # Sort the DataFrame for consistent ordering

# Hover was not showing the different wafers for a specific run so Increment ENTITY_DATA_COLLECT_DATE by 1 minute for each wfr so you can hover over each separately
df['ENTITY_DATA_COLLECT_DATE'] += df.groupby(['ENTITY', 'ENTITY_DATA_COLLECT_DATE', 'SPC_CHART_SUBSET']).cumcount().apply(
    lambda x: timedelta(minutes=x)
)

# Save the DataFrame to an Excel file
df.to_excel('df_data.xlsx', index=False)
# df.to_csv('df_data.csv', index=False)  # Optionally save to CSV

# Initialize the Dash app
app = dash.Dash(__name__)

# Get unique defect sizes
defect_sizes = df['SPC_CHART_SUBSET'].unique()

# Layout with radio button for filtering valid data
app.layout = html.Div([
    dcc.RadioItems(
        id='only-valid',
        options=[
            {'label': 'Only Valid Data', 'value': 'Y'},
            {'label': 'All Data', 'value': 'N'}
        ],
        value='Y',  # Default value
        labelStyle={'display': 'inline-block'}
    ),
    dcc.RadioItems(
        id='y-axis-scale',  # Radio button for y-axis scaling
        options=[
            {'label': 'Auto Scale', 'value': 'auto'},
            {'label': 'Use Upper Limit', 'value': 'upper_limit'},
            {'label': 'Manual', 'value': 'manual'}  # New manual option
        ],
        value='auto',  # Default value
        labelStyle={'display': 'inline-block'}
    ),
    dcc.Dropdown(
        id='manual-y-limit',  # New dropdown for manual y-axis limit
        options=[{'label': str(i), 'value': i} for i in range(15, 301, 15)],  # 15 to 300 in increments of 15
        value=30,  # Default value
        style={'width': '200px', 'display': 'inline-block', 'margin-left': '10px'}
    ),
    html.Div(id='charts-container')  # Container for the charts
])

# Callback to update charts based on radio button and dropdown selection
@app.callback(
    Output('charts-container', 'children'),
    [Input('only-valid', 'value'),
     Input('y-axis-scale', 'value'),
     Input('manual-y-limit', 'value')]  # New input for manual y-axis limit
)
def update_charts(only_valid, y_axis_scale, manual_y_limit):
    charts_by_resist = {}
    for resist in df['RESIST'].unique():
        # Filter data by resist
        resist_df = df[df['RESIST'] == resist]
        if only_valid == 'Y':
            # Further filter data to include only valid entries
            resist_df = resist_df[resist_df['VALID'] == 'Y']
        charts = []
        for defect_size in resist_df['SPC_CHART_SUBSET'].unique():
            # Filter data by defect size
            defect_size_df = resist_df[resist_df['SPC_CHART_SUBSET'] == defect_size]
            # Sort data by ENTITY_DATA_COLLECT_DATE
            defect_size_df = defect_size_df.sort_values(by=['ENTITY_DATA_COLLECT_DATE', 'FOUP_SLOT'], ascending=[True, True])
            # Add jitter to the y-axis (RAW_VALUE)
            defect_size_df['RAW_VALUE'] = defect_size_df['RAW_VALUE'] + np.random.uniform(-0.2, 0.2, size=len(defect_size_df))  # Add jitter of ±0.2
            # Get the last entries for monitor set name, chart test name, and measurement set name
            last_monitor_set_name = defect_size_df['MONITOR_SET_NAME'].iloc[-1]
            last_chart_test_name = defect_size_df['CHART_TEST_NAME'].iloc[-1]
            last_measurement_set_name = defect_size_df['MEASUREMENT_SET_NAME'].iloc[-1]
            # Create the title for the chart
            title = f'{resist} - {defect_size}<br>{last_monitor_set_name} {last_chart_test_name}<br>{last_measurement_set_name}'
            # Calculate the upper limit for the y-axis
            upper_limit = 2 * defect_size_df['UP_CONTROL_LMT'].iloc[-1]
            # Get the center line value
            center_line = defect_size_df['CENTERLINE'].iloc[-1]
            # Create hover text for each data point and add it as a column in the DataFrame
            defect_size_df['hovertext'] = defect_size_df.apply(
                lambda row: (
                    f'LOT: {row["LOT"]}<br>'
                    f'SLOT: {row["FOUP_SLOT"]}<br>'
                    f'WFR: {row["RAW_WAFER3"]}<br>'
                    f'ROUTE: {row["ROUTE"]}<br>'
                    f'FAIL: {row["FAIL"]}<br>'
                    f'VALID: {row["VALID"]}'
                ),
                axis=1
            )
            # Create the box plot
            fig = px.box(defect_size_df, x='ENTITY', y='RAW_VALUE', title=title, color='ENTITY')
            
            # Add a horizontal line for the upper control limit
            fig.add_hline(y=defect_size_df['UP_CONTROL_LMT'].iloc[-1], line_dash="dash", annotation_text="Upper Spec", line_color="red")
            # Add a horizontal line for the center line if it exists
            if pd.notna(center_line) and center_line != '':
                fig.add_hline(y=center_line, line_dash="dash", annotation_text="Center Line")

            # Update the layout with the y-axis range based on the selected scaling mode
            if y_axis_scale == 'upper_limit':
                fig.update_layout(yaxis_range=[0, upper_limit])
            elif y_axis_scale == 'manual':
                fig.update_layout(yaxis_range=[0, manual_y_limit])
            else:  # auto
                fig.update_layout(yaxis_autorange=True)

            # Update the layout for box plots
            fig.update_layout(
                hovermode="closest",
                hoverlabel=dict(
                    bgcolor="rgba(255, 255, 255, 0.33)",
                    font_size=12,
                    font_color="black",
                    bordercolor="rgba(0, 0, 0, 0)"
                ),
                xaxis=dict(
                    title="ENTITY"
                ),
                yaxis=dict(
                    fixedrange=False  # Allows y-axis zooming
                ),
                # Enable zoom controls
                dragmode='zoom',  # Default drag mode for zooming
                showlegend=True
            )

            # Append the chart to the list
            charts.append(dcc.Graph(figure=fig))
        # Store the charts by resist
        charts_by_resist[resist] = charts

    # Create the layout with 3 columns per row for each resist
    layout = []
    for resist, charts in charts_by_resist.items():
        # Group charts into rows of 3 columns
        rows = [charts[i:i + 3] for i in range(0, len(charts), 3)]
        resist_section = html.Div([
            html.H3(f'Resist: {resist}'),  # Add a header for each resist
            html.Div([
                html.Div(
                    [
                        html.Div(
                            chart,
                            style={
                                'flex': '1',  # Make each chart take up equal space
                                'margin': '5px'  # Add some spacing between charts
                            }
                        ) for chart in row
                    ],
                    className='row',
                    style={
                        'display': 'flex',
                        'flexDirection': 'row',
                        'width': '100%'  # Ensure the row takes the full width
                    }
                ) for row in rows
            ])
        ])
        layout.append(resist_section)

    return html.Div(layout)
    
# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)