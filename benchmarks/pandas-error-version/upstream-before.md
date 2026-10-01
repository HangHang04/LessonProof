# 上游讲义节选

原文件第 270–292 行，版本与 SHA-256 见 course.json。

````markdown
```python
surveys_df['weight'].astype("int")
```

```error
pandas.errors.IntCastingNaNError: Cannot convert non-finite values (NA or inf) to integer
```

Pandas cannot convert types from float to int if the column contains NaN values.

::::::::::::::::::::::::::::::::

::::::::::::::::::::::::::::::::::::::::::::::::::

## Missing Data Values - NaN

What happened in the last challenge activity? Notice that this throws a value error:
`ValueError: Cannot convert NA to integer`. If we look at the `weight` column in the surveys
data we notice that there are NaN (**N**ot **a** **N**umber) values. **NaN** values are undefined
values that cannot be represented mathematically. pandas, for example, will read
an empty cell in a CSV or Excel sheet as `NaN`. NaNs have some desirable properties: if we
were to average the `weight` column without replacing our NaNs, Python would know to skip
over those cells.
````
