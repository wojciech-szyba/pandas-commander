"""Snippet catalogs shown by the cmdPandas / cmdPolars / cmdPySpark / cmdDbt pickers.

Each catalog is a dict of `key -> (label, code)`. `label` is what the picker
list shows; `code` is inserted verbatim at the cursor when chosen.
"""
from __future__ import annotations

from textwrap import dedent


def _snippet(text: str) -> str:
    """Dedent a triple-quoted snippet and drop the leading/trailing blank line."""
    return dedent(text).strip("\n")


PANDAS_SNIPPETS: dict[str, tuple[str, str]] = {
    "read_csv": ("Read CSV", 'df = pd.read_csv("path/to/file.csv")'),
    "group_by": ("Group By", 'df.groupby("column").agg({"value": "sum"})'),
    "unique": ("Unique values", 'df["column"].unique()'),
    "merge": ("Merge", 'pd.merge(left, right, on="key", how="inner")'),
    "concat": ("Concat", 'pd.concat([df1, df2], axis=0)'),
    "pivot_table": (
        "Pivot table",
        'df.pivot_table(index="row", columns="col", values="value", aggfunc="sum")',
    ),
    "profiling": ("Profiling summary", _snippet("""
        summary = pd.DataFrame({
            "dtype": df.dtypes,
            "non_null": df.count(),
            "missing": df.isna().sum(),
            "missing_%": df.isna().mean().mul(100).round(1),
            "unique": df.nunique(),
        })
        print(summary)
        print(df.describe(include="all").T)
    """)),
    "write_df_as": ("Write to file", 'df.to_csv("filename", compression="gzip")'),
}

POLARS_SNIPPETS: dict[str, tuple[str, str]] = {
    "read_csv": ("Read CSV", 'df = pl.read_csv("path/to/file.csv")'),
    "group_by": ("Group By", 'df.group_by("column").agg(pl.col("value").sum())'),
    "unique": ("Unique values", 'df.select(pl.col("column").unique())'),
    "merge": ("Join", 'left.join(right, on="key", how="inner")'),
    "concat": ("Concat", 'pl.concat([df1, df2])'),
    "pivot": (
        "Pivot",
        'df.pivot(index="row", columns="col", values="value", aggregate_function="sum")',
    ),
    "profiling": ("Profiling summary", _snippet("""
        print(df.describe())
        print(df.null_count())
    """)),
    "write_df_as": ("Write to file", 'df.write_csv("filename.csv")'),
}

PYSPARK_SNIPPETS: dict[str, tuple[str, str]] = {
    "spark_init": ("Init SparkSession", _snippet("""
        from pyspark.sql import SparkSession

        spark = (
            SparkSession.builder
            .appName("DataPipeline")
            .config("spark.executor.memory", "4g")
            .getOrCreate()
        )
    """)),
    "spark_load_data": ("Load CSV -> Parquet", _snippet("""
        df = spark.read.csv("path/to/data.csv", header=True, inferSchema=True)
        df.write.mode("overwrite").parquet("path/to/output.parquet")
    """)),
    "spark_group_by": (
        "Group By",
        'df.groupBy("column").agg(F.sum("value").alias("value"))',
    ),
    "spark_join": ("Join", 'df = left.join(right, on="key", how="inner")'),
    "spark_date_conversion": (
        "Date conversion",
        'df = df.withColumn("date", F.to_date("date_str", "yyyy-MM-dd"))',
    ),
    "spark_nulls_handling": (
        "Null handling",
        'df = df.na.fill({"column": 0}).na.drop(subset=["other_column"])',
    ),
    "spark_struct": (
        "Struct column",
        'df = df.withColumn("info", F.struct(F.col("a"), F.col("b")))',
    ),
}

DBT_SNIPPETS: dict[str, tuple[str, str]] = {
    "dbt_model": ("New model", _snippet("""
        {{ config(materialized='table') }}

        select *
        from {{ ref('source_table') }}
    """)),
    "dbt_incremental": ("Incremental model", _snippet("""
        {{ config(materialized='incremental', unique_key='id') }}

        select *
        from {{ source('raw', 'events') }}
        {% if is_incremental() %}
        where event_time > (select max(event_time) from {{ this }})
        {% endif %}
    """)),
    "dbt_ref": ("ref() macro", "{{ ref('model_name') }}"),
    "dbt_source": ("source() macro", "{{ source('schema_name', 'table_name') }}"),
    "dbt_schema_yml": ("schema.yml boilerplate", _snippet("""
        version: 2

        models:
          - name: model_name
            description: ""
            columns:
              - name: id
                tests:
                  - unique
                  - not_null
    """)),
    "dbt_singular_test": ("Singular test", _snippet("""
        select *
        from {{ ref('model_name') }}
        where condition
    """)),
    "dbt_macro": ("Macro boilerplate", _snippet("""
        {% macro macro_name(column_name) %}
            {{ column_name }}
        {% endmacro %}
    """)),
}

# Registry keyed by the picker command name (pandas/polars/pyspark/dbt) ->
# (dialog title, snippet catalog).
LIBRARIES: dict[str, tuple[str, dict[str, tuple[str, str]]]] = {
    "pandas": ("Pandas snippets", PANDAS_SNIPPETS),
    "polars": ("Polars snippets", POLARS_SNIPPETS),
    "pyspark": ("PySpark snippets", PYSPARK_SNIPPETS),
    "dbt": ("dbt snippets", DBT_SNIPPETS),
}
