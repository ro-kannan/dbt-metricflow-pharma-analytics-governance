{{ config(materialized='table') }}

select
    unnest(generate_series(date '2024-01-01', date '2025-12-31', interval '1 day'))::date as date_day
