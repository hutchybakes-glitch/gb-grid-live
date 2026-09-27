{#- Helpers for reading raw JSON files written by the ingestion pipeline. -#}

{% macro raw_glob(source) -%}
    {#- Glob for every raw file of one source. The raw folder is configurable so
        pipeline.run can pass an absolute path regardless of working directory. -#}
    '{{ env_var("GBGL_RAW_DIR", "../data/raw") | replace("\\", "/") }}/{{ source }}/*/*.json'
{%- endmacro %}

{% macro ci_ts(col) -%}
    {#- Carbon Intensity times look like 2023-01-01T00:00Z (always UTC). -#}
    strptime({{ col }}, '%Y-%m-%dT%H:%MZ')
{%- endmacro %}

{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- Use the layer name as the schema (bronze, silver ...) instead of dbt's
        default "<target>_<layer>", which reads badly in a single-user warehouse. -#}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
