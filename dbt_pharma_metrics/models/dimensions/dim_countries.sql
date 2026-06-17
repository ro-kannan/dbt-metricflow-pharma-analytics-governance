with countries as (
    select distinct country_id from {{ ref('stg_sales') }}
)

select
    country_id,
    case country_id
        when 'US' then 'United States'
        when 'UK' then 'United Kingdom'
        when 'DE' then 'Germany'
        when 'JP' then 'Japan'
    end as country_name,
    case country_id
        when 'US' then 'USD'
        when 'UK' then 'GBP'
        when 'DE' then 'EUR'
        when 'JP' then 'JPY'
    end as currency,
    case country_id
        when 'US' then 'Americas'
        when 'UK' then 'EMEA'
        when 'DE' then 'EMEA'
        when 'JP' then 'APAC'
    end as region
from countries
