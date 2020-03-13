# Omit tag recovery

## Omit rules

### 'on' in Time relation

> ある基本タグXと，ある時間タグTとの間のon関係は，Xの直前の基本タグYが同じ時間タグTとon関係をもつ場合には省略してよい．

DCT-Rel also follows.

### 'value' in Basic relation

T/M-key --- value

1:1　で連続している時は省略可能

### 同格

> 同格関係にある複数のDからのregion関係はどれか1つから伸ばせば良く，他は省略可

同格のD?


## Brat 'ann' file specs

### file format

TSV of `ID\tSpan\tRef`

`Span` = (type, start-offset, end-offset)

Space-separated.
end-offset is an exclusive index.

### Annotation ID

- T: text-bound annotation
- R: relation
- E: event
- A: attribute
- M: modification (alias for attribute, for backward compatibility)
- N: normalization [new in v1.3]
- #: note

After these notations, a serial number continues (e.g. `T1`, `R14`).

### Entity

`T1\tAnatomical 434 439\tＣＨＥＳＴ`

### Relation

`R1\t[type] Arg1:T3 Arg2:T4`

### Attribute

`A2\t[type] [Entity/Relation ID] [value]`
