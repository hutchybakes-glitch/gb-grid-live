{#- Small generic tests, so the project needs no external dbt packages. -#}

{% test unique_combination(model, columns) %}
    {#- Fails for each key combination that appears more than once. -#}
    select {{ columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ columns | join(', ') }}
    having count(*) > 1
{% endtest %}

{% test between(model, column_name, min_value, max_value) %}
    {#- Nulls pass: "not null" is a separate test where it applies. -#}
    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }}
{% endtest %}
