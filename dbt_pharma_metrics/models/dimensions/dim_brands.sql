with brands as (
    select distinct brand_id from {{ ref('stg_sales') }}
)

select
    brand_id,
    case brand_id
        when 'BR001' then 'Cardivex'
        when 'BR002' then 'Oncovance'
        when 'BR003' then 'Respira'
        when 'BR004' then 'Neuroplex'
        when 'BR005' then 'Immunex'
    end as brand_name,
    case brand_id
        when 'BR001' then 'cardiovascular'
        when 'BR002' then 'oncology'
        when 'BR003' then 'respiratory'
        when 'BR004' then 'neurology'
        when 'BR005' then 'immunology'
    end as therapeutic_class,
    case brand_id
        when 'BR001' then 'statin'
        when 'BR002' then 'taxane'
        when 'BR003' then 'inhaled_corticosteroid'
        when 'BR004' then 'anticonvulsant'
        when 'BR005' then 'anti_tnf'
    end as sub_class,
    case brand_id
        when 'BR001' then 'atorvastatin-x'
        when 'BR002' then 'paclitab-3'
        when 'BR003' then 'flutico-b2'
        when 'BR004' then 'gabap-er'
        when 'BR005' then 'adalim-biosim'
    end as molecule
from brands
