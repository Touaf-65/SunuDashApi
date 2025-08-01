from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncYear
import pytz

tz = pytz.UTC


def get_granularity(date_start, date_end):
    """
    Determines the optimal granularity based on the period.
    
    Args:
        date_start (datetime): Start date
        date_end (datetime): End date
        
    Returns:
        str: 'day', 'month', 'quarter', or 'year'
    """
    delta = date_end - date_start
    if delta.days <= 31:
        return 'day'
    elif delta.days <= 365:
        return 'month'
    elif delta.days <= 5 * 365:
        return 'quarter'
    else:
        return 'year'


def get_trunc_function(granularity):
    """
    Returns the appropriate Django truncation function.
    
    Args:
        granularity (str): 'day', 'month', 'quarter', or 'year'
        
    Returns:
        Function: Django truncation function
    """
    trunc_map = {
        'day': TruncDay,
        'month': TruncMonth,
        'quarter': TruncQuarter,
        'year': TruncYear
    }
    return trunc_map.get(granularity, TruncMonth)


def parse_date_range(date_start_str, date_end_str):
    """
    Parses and validates a date range.
    
    Args:
        date_start_str (str): Start date in YYYY-MM-DD format
        date_end_str (str): End date in YYYY-MM-DD format
        
    Returns:
        tuple: (date_start, date_end) as timezone-aware datetime objects
        
    Raises:
        ValueError: If the date format is invalid
    """
    if not (date_start_str and date_end_str):
        raise ValueError("date_start and date_end are required.")
    
    try:
        date_start = tz.localize(datetime.strptime(date_start_str, "%Y-%m-%d"))
        date_end = tz.localize(datetime.strptime(date_end_str, "%Y-%m-%d"))
        return date_start, date_end
    except ValueError:
        raise ValueError("Invalid date format. Use YYYY-MM-DD.")


def to_timestamp_ms(dt):
    """
    Converts a date to a millisecond timestamp.
    
    Args:
        dt: datetime, date, or timestamp
        
    Returns:
        int: Timestamp in milliseconds
    """
    if hasattr(dt, 'timestamp'):
        return int(dt.timestamp() * 1000)
    elif isinstance(dt, date):
        return int(datetime(dt.year, dt.month, dt.day).timestamp() * 1000)
    else:
        return int(dt)


def serie_to_pairs(serie):
    """
    Converts a data series into [timestamp, value] pairs for ApexCharts.
    
    Args:
        serie (list): List of dictionaries with 'period' and 'value'
        
    Returns:
        list: List of [timestamp_ms, value] pairs
    """
    return [[to_timestamp_ms(point['period']), float(point['value'] or 0)] for point in serie]


def generate_periods(date_start, date_end, granularity):
    """
    Generates all periods between two dates according to the granularity.
    
    Args:
        date_start (datetime): Start date
        date_end (datetime): End date
        granularity (str): 'day', 'month', 'quarter', or 'year'
        
    Returns:
        list: List of generated periods
    """
    periods = []
    current = date_start
    
    while current <= date_end:
        periods.append(current)
        if granularity == 'day':
            current += timedelta(days=1)
        elif granularity == 'month':
            current += relativedelta(months=1)
        elif granularity == 'quarter':
            current += relativedelta(months=3)
        else:  # year
            current += relativedelta(years=1)
    
    return periods


def to_date(obj):
    """
    Converts an object to a date.
    
    Args:
        obj: datetime, date, or another object
        
    Returns:
        date: Date object
    """
    if hasattr(obj, 'date'):
        return obj.date()
    elif isinstance(obj, datetime):
        return obj.date()
    return obj


def fill_full_series(periods, serie):
    """
    Fills a series with all periods, propagating the last known value.
    
    Args:
        periods (list): List of all periods
        serie (list): Original data series
        
    Returns:
        list: Complete series with all periods
    """
    value_map = {to_date(point['period']): point['value'] for point in serie}
    last_value = None
    result = []
    
    for period in periods:
        period_date = to_date(period)
        if period_date in value_map:
            last_value = value_map[period_date]
        result.append({'period': period, 'value': last_value})
    
    return result


def date_label(dt, granularity):
    """
    Generates a date label according to the granularity.
    
    Args:
        dt: Date/datetime object
        granularity (str): 'day', 'month', 'quarter', or 'year'
        
    Returns:
        str: Formatted label
    """
    if granularity == 'day':
        if hasattr(dt, 'strftime'):
            return dt.strftime('%a')  # 'Mon', 'Tue', ...
        return str(dt)
    elif granularity == 'month':
        if hasattr(dt, 'strftime'):
            return dt.strftime('%Y-%m')
        return str(dt)
    elif granularity == 'year':
        if hasattr(dt, 'strftime'):
            return dt.strftime('%Y')
        return str(dt)
    elif granularity == 'quarter':
        if hasattr(dt, 'year') and hasattr(dt, 'month'):
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        return str(dt)
    return str(dt)


def compute_evolution_rate(series):
    """
    Calculates the evolution rate between the first and last point of a series.
    
    Args:
        series (list): Data series
        
    Returns:
        float or str: Evolution rate as a percentage or "New"
    """
    if not series or len(series) == 0:
        return 0.0
        
    if len(series) == 1:
        first = last = float(series[0]['value'] or 0)
    else:
        first = float(series[0]['value'] or 0)
        last = float(series[-1]['value'] or 0)
    
    if first == 0:
        if last == 0:
            return 0.0
        else:
            return "New"
    
    return round(100 * (last - first) / abs(first), 2)


def format_series_for_multi_line_chart(series_dict, periods, granularity, role_labels=None):
    """
    Formats multiple series for an ApexCharts multi-line chart.
    
    Args:
        series_dict (dict): Dictionary of series by role/type
        periods (list): List of periods
        granularity (str): Temporal granularity
        role_labels (dict): Custom labels for roles
        
    Returns:
        list: Formatted series for ApexCharts
    """
    if role_labels is None:
        role_labels = {}
    
    period_dates = set([to_date(p) for p in periods])
    result_series = []
    
    for role, serie in series_dict.items():
        label = role_labels.get(role, role)
        
        # Index of values from the original series
        value_map = {to_date(point['period']): float(point['value'] or 0) for point in serie}
        
        # Off-grid points
        extra_dates = set(value_map.keys()) - period_dates
        
        # Merges and sorts all dates
        all_dates = sorted(period_dates | extra_dates)
        
        data = []
        for d in all_dates:
            if d in period_dates:
                x = date_label(d, granularity)
            else:
                # Special label for off-grid
                x = f"EXTRA {d}"
            y = value_map.get(d, 0)
            data.append({'x': x, 'y': y})
        
        result_series.append({'name': label, 'data': data})
    
    return result_series


def format_top_clients_series(top_clients_data, periods, granularity):
    """
    Formats top clients' data for ApexCharts.
    
    Args:
        top_clients_data (list): Top clients data
        periods (list): List of periods
        granularity (str): Temporal granularity
        
    Returns:
        tuple: (series_multi, categories)
    """
    period_dates = [to_date(p) for p in periods]
    series_multi = []
    
    for top in top_clients_data:
        name = top.get("client_name") or str(top.get("client_id"))
        value_map = {to_date(point['period']): float(point['value'] or 0) 
                    for point in top["series"]}
        data = [value_map.get(p, 0) for p in period_dates]
        series_multi.append({"name": name, "data": data})
    
    categories = [date_label(p, granularity) for p in period_dates]
    
    return series_multi, categories