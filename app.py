from flask import Flask, render_template, request
from datetime import datetime, date
from sqlalchemy import create_engine
from bokeh.models import ColumnDataSource, HoverTool, Square,LinearAxis,Grid
from bokeh.io import output_file, output_notebook
from bokeh.plotting import figure, show,curdoc
from bokeh.embed import components
import yfinance as yf
import pandas as pd
import numpy as np
import math

# .\venv\Scripts\activate

 
app = Flask(__name__)

def add_position(df):
    df['Position'] = "N/A"
    for i, row in df.iterrows():
        if df.loc[i,"Short_MA"] > df.loc[i,'Long_MA']:
            df.loc[i, "Position"] = "Long"
        elif df.loc[i,"Short_MA"] < df.loc[i,'Long_MA']:
            df.loc[i, "Position"] = "Short"
        else:
            df.loc[i, "Position"] = None
    return df

def get_price_data(ticker, period='max'):
    s=yf.Ticker(ticker).history(period)['Close'] 
    return s#returns Pandas Series of close price data for given ticker

def add_moving_avgs(df, short, long): 
    df['Short_MA'] = df.rolling(short)['Close'].mean()
    df['Long_MA'] = df.rolling(long)['Close'].mean()   
#date filtering parameters start + end default to none, pass strings in "YYYY-MM-DD" format to filter
def render_short_long_ma(ticker, short=10, long=30, start=None, end=None):
    #Setting default canvas when users first enter
    if ticker is None:
        fig = figure(plot_height=400, plot_width=800,
                     toolbar_location='right', tools=['pan','wheel_zoom','save','reset'])
        return fig
    df = pd.DataFrame(get_price_data(ticker)) #Convert data from yfinance into panda dataframe
    #s=df.reset_index()
    add_moving_avgs(df, short, long)
    add_position(df)
    #add_moving_avgs(s, short, long)
    #Bokeh plots use ColumnDataSource, so convert DataFrame to that
    #Change date range and type here
    if start is not None and end is not None:
        s=df.loc[start:end] #s is a fix for y-finance. Data times are not a separate column but an index from the orginal data. 
                            #So I copied the df and hope to single out data times later when we're drawing squares :).
        price_data = ColumnDataSource(df.loc[start:end])
    else:
        s=df
        price_data = ColumnDataSource(df)

    #Create a figure to display data
    #Set tools here with the exception of HoverTool, which we add later so it only renders tooltips for the close price line
    fig = figure(title=ticker+' Price',
                 x_axis_type='datetime',
                 plot_height=400, plot_width=800,
                 toolbar_location='right', tools=['pan','wheel_zoom','save','reset'],
                 x_axis_label='Date',y_axis_label = 'Price')
    #Change Font Size
    fig.title.text_font_size = '10pt'
    fig.xaxis.axis_label_text_font_size='10pt'
    fig.yaxis.axis_label_text_font_size='10pt'
    
    #store close price glyph as g, later use g to create HoverTool
    g = fig.line('Date', 'Close',
                 color='blue',
                 legend_label="Daily Closing Price",
                 line_width=1, source=price_data)
    fig.line('Date', 'Short_MA',
             color='orange', 
             legend_label="Short-Term Moving Average",
             line_width=1, source=price_data)
    fig.line('Date', 'Long_MA',
             color='black', 
             legend_label="Long-Term Moving Average",
             line_width=1, source=price_data)
    #Drawing Squares
    square_x=[]
    square_y=[]
    s=s.reset_index()
    for i in range(1, len(s.index)):
        if s['Position'][i]!=s['Position'][i-1]:
            square_x.append(s['Date'][i])
            square_y.append(s['Close'][i])
    fig.square(square_x, square_y, size = 8, color = 'red', legend_label='Cross Point')
    
    fig.legend.location = 'top_left'
    
    #fig.square(x='Date',y='Short_MA', color='red') #an example for making a square for m_a crossovers
    
    #Only want the HoverTool to show g (the close price line)
    fig.add_tools(HoverTool(renderers=[g],
        tooltips=[
            ( 'Date',   '@Date{%Y-%m-%d}'), #left side is name in tooltip, right side is name in ColumnDataSource
            ( 'Price',  '$@Close{%0.2f}' ), #use @{ } for field names with spaces, {} also used for formatting
        ],
        formatters={
            'Date':'datetime',
            'Close':'printf'
        },
        mode='vline' #display tooltip of price vertically above/below cursor
    ))
    fig.min_border_left = 0
    fig.min_border_right = 0
    fig.min_border_top = 0
    fig.min_border_bottom = 0
    #set to output into notebook, down the road we'll use output_file to setup display for flask
    output_notebook()
    #show(fig)
    return fig

def sharpe_ratio_counter(ticker, execute_period):
    df = counterTrend(pd.DataFrame(get_price_data(ticker)), execute_period=int(execute_period))
        
    #Calculate the daily returns
    df['% Change'] = df['Close'].pct_change()
    
    #Take the average of all returns
    avg_ret = df['% Change'][execute_period:].mean()
    
    #Taking the standard deviation of the returns gives us a measure of volatility (price fluctiation), and thus a proxy for risk
    std_dev = df['% Change'][execute_period:].std()
    
    #Sharpe ratio formula: 252 figure represents the number of trading days in a year and is used to annualize the metrics 
    sharpe = (math.sqrt(252)*avg_ret)/std_dev
    return round(sharpe,3)

def sharpe_ratio(ticker,short,long):
    df = pd.DataFrame(get_price_data(ticker))
    add_moving_avgs(df, short, long)
    df['Daily Return'] = df['Close'].pct_change(1)
    averages = df['Daily Return'][long:].mean()
    std_dev = df['Daily Return'][long:].std()   
    annualize = math.sqrt(260)
    sharpe_ratio = (annualize*averages)/(std_dev)
    sharpe_ratio = round(sharpe_ratio,3)
    return sharpe_ratio

def counterTrend(df, execute_period):
    # Create a column and set positions to null values
#    df['Position'] = "N/A" 
    
    #Calculate the period high and low to set threshold for when to execute a position
    df["High Check"] = df.rolling(execute_period)['Close'].max()
    df["Low Check"] = df.rolling(execute_period)['Close'].min()
    
    #Have to shift the values down one position to make current day close price comparable to most recent
    #high or low since close prices are end of day metrics
    df[str(execute_period)+' Day High'] = df["High Check"].shift(1)
    df[str(execute_period)+' Day Low'] = df["Low Check"].shift(1)
    
    #Remove unnecessary columns from dataframe 
    df.drop(labels=["High Check", "Low Check"], axis = "columns", inplace=True)
    
    #Calculate the position --> Close Price > period high = Long; Close Price < period low = Short; Else = Hold
    for i, row in df.iterrows():
        if df.loc[i,"Close"] > df.loc[i,str(execute_period)+' Day High']:
            df.loc[i,'Position'] = "Short"
        elif df.loc[i,"Close"] < df.loc[i,str(execute_period)+' Day Low']:
            df.loc[i,'Position'] = "Long"
        else:
            df.loc[i,'Position'] = "Hold"
 
    return df

def render_counterTrend(ticker, execute_period):
    if ticker is None:
        fig = figure(plot_height=400, plot_width=800,
                     toolbar_location='right', tools=['pan','wheel_zoom','save','reset'])
        return fig
    df_0=pd.DataFrame(get_price_data(ticker))
    df=counterTrend(df_0, execute_period)
    #Converting df into Column data source
    #if start is not None and end is not None:
        #s=df.loc[start:end]
        #price_data = ColumnDataSource(df.loc[start:end])
    #else:
    s=df
    price_data = ColumnDataSource(df)
    # setting default when users first enter
    fig = figure(title=f'{ticker} Price',
                 x_axis_type='datetime',
                 plot_height=400, plot_width=800,
                 toolbar_location='right', tools=['pan','wheel_zoom','save','reset'],
                 x_axis_label='Date',y_axis_label = 'Price')
    fig.title.text_font_size = '10pt'
    fig.xaxis.axis_label_text_font_size='10pt'
    fig.yaxis.axis_label_text_font_size='10pt'
    #store close price glyph as g, later use g to create HoverTool
    g = fig.line('Date', 'Close',
                 color='blue',
                 legend_label="Daily Closing Price",
                 line_width=1, source=price_data)
    fig.line('Date', str(execute_period)+' Day High',
             color='orange', 
             legend_label=str(execute_period)+' Day High',
             line_width=1, source=price_data)
    fig.line('Date', str(execute_period)+' Day Low',
             color='black', 
             legend_label=str(execute_period)+' Day Low',
             line_width=1, source=price_data)
    # Drawing cross points as squares
    square_x=[]
    square_y=[]
    s=s.reset_index()
    for i in range(1, len(s.index)):
        if s['Position'][i]!=s['Position'][i-1]:
            square_x.append(s['Date'][i])
            square_y.append(s['Close'][i])
    fig.square(square_x, square_y, size = 4, color = 'red', legend_label='Cross Point')
    
    #Only want the HoverTool to show g (the close price line)
    fig.add_tools(HoverTool(renderers=[g],
        tooltips=[
            ( 'Date',   '@Date{%Y-%m-%d}'), #left side is name in tooltip, right side is name in ColumnDataSource
            ( 'Price',  '$@Close{%0.2f}' ), #use @{ } for field names with spaces, {} also used for formatting
        ],
        formatters={
            'Date':'datetime',
            'Close':'printf'
        },
        mode='vline' #display tooltip of price vertically above/below cursor
    ))
    #set to output into notebook, down the road we'll use output_file to setup display for flask
    output_notebook()
    #show(fig)
    return fig
    

@app.route('/moving-avg')
def moving_avg():
    start = request.args.get('start')
    end = request.args.get('end')
    short = request.args.get('short')
    long = request.args.get('long')
    ticker = request.args.get('ticker')
    strategy = request.args.get('strategy')
    if not isinstance(short, int):
        short = 10
    if not isinstance(long, int):
        long = 30
    plot = render_short_long_ma(ticker, short=int(short), long=int(long), start=start, end=end)
    script, div = components(plot)
    if not isinstance(ticker, str):
        sharpe = ''
    else: sharpe = sharpe_ratio(ticker, short, long)
    return render_template('moving-avg.html', script=script, div=div, start=start, end=end, short=short, long=long, ticker=ticker, strategy=strategy, sharpe=sharpe)


@app.route('/counter-trend')
def counter_trend():
    ep = request.args.get('ep')
    ticker = request.args.get('ticker')
    if not isinstance(ep, int):
        ep = 100
    plot = render_counterTrend(ticker, execute_period=int(ep))
    script, div = components(plot)
    if not isinstance(ticker, str):
        sharpe = ''
    else: sharpe = sharpe_ratio_counter(ticker, int(ep))
    return render_template('counter-trend.html', script=script, div=div, ticker=ticker, ep=ep, sharpe=sharpe)

@app.route('/')
def splash():
    return render_template('splash.html')

app.run(threaded=True)