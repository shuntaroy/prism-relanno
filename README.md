# PRISM-RelAnno

Visualise relation annotations for human.

## Usage

- `recover_omit.py` で省略された関係を復元した `-r.ann`ファイルを作る
- `visualise_rel.py` で基本関係のdot scriptがstdoutされるので，graphvizできる
- `visualise_time.py` は時間関係

### use as a library

`entity_types.py` に便利なクラスがいろいろあるので，bratからpython-readableなobjectを作って好きな用途に使用できる．

APIとしては…


## TODOs

- [ ] `visualise_*`は統一して良さそう
- [ ] docs (using pyment to autogen, then include doctest...?)
- [ ] Search API adapted from [Cypher](https://neo4j.com/developer/cypher-query-language/)


-----------------------------------
# Appendix

Related notes for reference.

## Omit rules

### 'on' in Time relation

> ある基本タグXと，ある時間タグTとの間のon関係は，Xの直前の基本タグYが同じ時間タグTとon関係をもつ場合には省略してよい．

DCT-Rel also follows.

### 'value' in Basic relation

T/M-key --- value

1:1　で連続している時は省略可能

<!-- ### 同格関係の複数タグから付与する region 関係

> 同格関係にある複数のDからのregion関係はどれか1つから伸ばせば良く，他は省略可

`A1-region->D1, A1-region->D2 s.t. D1==D2`
then `D1/D2-region->A2` (etc.) can be omitted. -->

## Brat 'ann' file specs

### file format

TSV of `ID\tSpan\tRef`

`Span` = (type, start-offset, end-offset)

Space-separated.
End-offset is an exclusive index.

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
