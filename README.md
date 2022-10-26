# For HeaRT-API

See [`./README-API.md`](./README-API.md) instead.

---

# PRISM-RelAnno

Visualise relation annotations for human.

> This project is under my personal use yet.

## Requirements

- Python 3.6--3.8 (not compatible with 3.9 due to old type hints)

## Usage

- `recover_omit.py` で省略された関係を復元した `-r.ann`ファイルを作る
- `visualise_rel.py` で基本関係の dot script が stdout されるので，graphviz できる
- `visualise_time.py` は時間関係を処理する．同じ時点に属する Entity を TimeContainer にまとめる，など．

### Timeline information for HeaRT input

Given a Brat's `.ann` file annotated with PRISM guidelines, the DCT of which is 2014-03-20, run:

```
$ python recover_omit.py XXX.ann  # this creates XXX-r.ann (and XXX-r.txt)
$ python visualise_time.py XXX-r.ann 2014-03-20 > XXX.json
```

#### WIP/TODO features

- [ ] Infer anatomical structures from knowledge base
- [ ] Input from XML formatted files

### use as a library

`entity_types.py` に便利なクラスがいろいろあるので，brat から python-readable な object を作って好きな用途に使用できる．

API としては…

## TODOs for Refactor/Improvement

- [ ] `visualise_*`は統一して良さそう
- [ ] docs (using pyment to autogen, then include doctest...?)
- [ ] Search API adapted from [Cypher](https://neo4j.com/developer/cypher-query-language/)

## Notes

---

# Appendix

Related notes for reference.

## Omit rules

### 'on' in Time relation

> ある基本タグ X と，ある時間タグ T との間の on 関係は，X の直前の基本タグ Y が同じ時間タグ T と on 関係をもつ場合には省略してよい．

DCT-Rel also follows.

### 'value' in Basic relation

T/M-key --- value

1:1 　で連続している時は省略可能

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
