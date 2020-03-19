from __future__ import annotations
import sys
from typing import List, Dict, Tuple, NewType, TypeVar, Set

Id = NewType("Id", int)
A = TypeVar("A")


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

    def __hash__(self):
        return hash((self.name, self.arg1, self.arg2))

    def __eq__(self, other):
        _name = self.name == other.name
        _arg1 = self.arg1 == self.arg1
        _arg2 = self.arg2 == self.arg2
        return all([_name, _arg1, _arg2])


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

    def __hash__(self):
        return hash((self.name, self.target, self.value))

    def __eq__(self, other):
        _name = self.name == other.name
        _target = self.target == other.target
        _value = self.value == other.value
        return all([_name, _target, _value])


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


class Entity:
    """Struct of an entity."""

    excl_time = ["Anatomical", "Feature", "Pending"]

    def __init__(self, _id: Id, tag: str, span: Tuple[int, int], text: str):
        self.id = _id
        self.tag = tag
        self.span = span
        self.text = text

        self.attrs: Dict[str, Attribute] = {}
        self.rels: Dict[str, Set[Relation]] = {}
        self.others: List[Other] = []

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

    def set_attribute(self, attribute: Attribute) -> None:
        self.attrs[attribute.name] = attribute

    def set_relation(self, relation: Relation) -> None:
        self.rels.setdefault(relation.name, set()).add(relation)

    def set_other(self, other: Other) -> None:
        self.others.append(other)


class Document:
    """Store of all annotations."""

    def __init__(self, filename: str):
        self.entities: List[Entity] = []
        self.attributes: List[Attribute] = []
        self.relations: List[Relation] = []
        self.others: List[Other] = []

        # store maximum IDs
        self.ent_id_max = 0
        self.attr_id_max = 0
        self.rel_id_max = 0
        self.other_id_max = 0

        # states
        self.built = False

        with open(filename, "r") as fi:
            for line in fi:
                self.read_ann_line(line.strip())

        self.build_doc()

    def read_ann_line(self, line: str) -> None:
        assert self.built is False

        if line.startswith("T"):
            self.entities.append(Entity.from_raw(line))
        elif line.startswith("A"):
            self.attributes.append(Attribute.from_raw(line))
        elif line.startswith("R"):
            self.relations.append(Relation.from_raw(line))
        else:
            self.others.append(Other.from_raw(line))

    def build_doc(self):
        """Update entities with attributes and relations."""
        assert self.built is False

        self.ent_id_max = max(*[e.id for e in self.entities])

        for attr in self.attributes:
            self.attr_id_max = max(self.attr_id_max, attr.id)
            e: Entity = self.findby_id(attr.target)
            e.set_attribute(attr)

        for rel in self.relations:
            self.rel_id_max = max(self.rel_id_max, rel.id)
            e = self.findby_id(rel.arg1)
            e.set_relation(rel)

        for other in self.others:
            self.other_id_max = max(self.other_id_max, other.id)
            e = self.findby_id(rel.arg1)
            e.set_other(other)

        self.attributes = []
        self.relations = []
        self.built = True

    def findby_id(self, _id: Id) -> Entity:
        """Find an entity specified by the ID"""
        es = [e for e in self.entities if e.id == _id]
        assert len(es) == 1, "Containing IDs are not unique"
        return es[0]

    def sortedby_occurrence(self, tgt_anno: str = "entities") -> None:
        assert self.built is True

        setattr(
            self, tgt_anno, sorted(getattr(self, tgt_anno), key=lambda e: e.span[0])
        )

    def update_attribute(self, attrtype: str, target: Id, value: str) -> None:
        assert self.built is True

        self.attr_id_max += 1
        new_attr = Attribute(
            _id=Id(self.attr_id_max), name=attrtype, target=target, value=value
        )
        self.findby_id(target).set_attribute(new_attr)

    def add_relation(self, reltype: str, arg1: Id, arg2: Id) -> None:
        assert self.built is True

        self.rel_id_max += 1
        new_rel = Relation(_id=Id(self.rel_id_max), name=reltype, arg1=arg1, arg2=arg2)
        self.findby_id(arg1).set_relation(new_rel)

    def output_ann(self, fout=sys.stdout):
        assert self.built is True

        for e in self.entities:
            for attrtype, attr in e.attrs.items():
                self.attributes.append(attr)
            for reltype, rels in e.rels.items():
                self.relations.extend(rels)

        self.attributes = sorted(self.attributes, key=lambda a: a.id)
        self.relations = sorted(self.relations, key=lambda r: r.id)

        annotations: List[list] = [
            self.entities,
            self.relations,
            self.attributes,
            self.others,
        ]

        for anno in annotations:
            for a in anno:
                if a is not None:
                    print(a, file=fout)
