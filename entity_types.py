from __future__ import annotations
from typing import List, Dict, Tuple, NewType, Union

Id = NewType("Id", int)

# TODO: entityにrelや他の属性を全て持たせる
# TODO: entity以外のクラスを廃止する


class Entity:
    """Struct of an entity."""

    def __init__(self, _id: Id, tag: str, span: Tuple[int, int], text: str):
        self.id = _id
        self.tag = tag
        self.span = span
        self.text = text
        self.rels: Dict[str, List[Id]] = {}

    @classmethod
    def from_raw(cls, raw_line: str) -> Entity:
        _id, raw_span, text = raw_line.split("\t")
        tag, begin, end = raw_span.split(" ")
        return cls(
            _id=Id(int(_id[1:])), tag=tag, span=(int(begin), int(end)), text=text,
        )

    def __repr__(self):
        return f"<T{self.id} {self.tag} {self.text}>"

    def __str__(self):
        return f"T{self.id}\t{self.tag} {self.span[0]} {self.span[1]}\t{self.text}"


class Relation:
    """Struct of a relation."""

    def __init__(self, _id: Id, name: str, arg1: Id, arg2: Id):
        self.id = _id
        self.name = name
        self.arg1 = arg1
        self.arg2 = arg2

    @classmethod
    def from_raw(cls, raw_line: str) -> Relation:
        _id, raw_rel = raw_line.split("\t")
        name, arg1, arg2 = raw_rel.split(" ")
        return cls(
            _id=Id(int(_id[1:])),
            name=name,
            arg1=Id(int(arg1.split(":T")[1])),
            arg2=Id(int(arg2.split(":T")[1])),
        )

    def __repr__(self):
        return f"<R{self.id} {self.name} {self.arg1}->{self.arg2}>"

    def __str__(self):
        return f"R{self.id}\t{self.name} Arg1:T{self.arg1} Arg2:T{self.arg2}"


class Attribute:
    """Struct for an attribute"""

    def __init__(self, _id: Id, name: str, target: Id, value: str):
        self.id = _id
        self.name = name
        self.target = target
        self.value = value

    @classmethod
    def from_raw(cls, raw_line: str) -> Attribute:
        _id, raw_attr = raw_line.split("\t")
        name, target, value = raw_attr.split(" ")
        return cls(
            _id=Id(int(_id[1:])), name=name, target=Id(int(target[1:])), value=value
        )

    def __repr__(self):
        return f"<A{self.id} T{self.target}.{self.name}={self.value}>"

    def __str__(self):
        return f"A{self.id}\t{self.name} T{self.target} {self.value}"


class Other:
    """Struct for other ann lines"""

    def __init__(self, *cols: str):
        self.cols = cols
        self.id = Id(int(cols[0][1:]))

    @classmethod
    def from_raw(cls, raw_line: str) -> Other:
        cols = raw_line.split("\t")
        return cls(*cols)

    def __repr__(self):
        return f"<{self.cols}>"

    def __str__(self):
        return "\t".join(self.cols)


Items = Union[List[Entity], List[Attribute], List[Relation], List[Other]]
Item = Union[Entity, Attribute, Relation, Other]


def findby_id(items: Items, _id: Id) -> Item:
    es = [e for e in items if e.id == _id]
    assert len(es) == 1, "Containing IDs are not unique"
    return es[0]
