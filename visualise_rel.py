"""Visualise basic relations into trees and tables."""
import sys
from typing import List, Dict, Set

import fire

from entity_types import Id, Document, Entity, Relation

CLR = {
    "Disease": "orangered",
    "Anatomical": "orange",
    "Feature": "deepskyblue",
    "Change": "green",
    "TestTest": "yellow",
    "TestKey": "yellow",
    "TestVal": "yellow",
    "MedicineKey": "pink",
    "MedicineVal": "pink",
    "Remedy": "gray",
    "ClinicalContext": "brown",
    "Pending": "white",
    "TIMEX3": "violet",
}


def resolve_rel(doc: Document) -> None:
    assert doc.built

    # create the DCT entity
    dct = Entity(Id(-1), "TIMEX3", (-1, 0), "DCT")
    doc.entities.append(dct)

    # inverse relations for parent entities
    n = len(doc.entities)
    for i in range(n):
        for reltype, rels in doc.entities[i].rels_to.items():
            for rel in rels:
                e: Entity = doc.findby_id(rel.arg2)
                e.set_relation_from(reltype, doc.entities[i])
        dct_rel = doc.entities[i].attrs.get("DCT-Rel")
        if dct_rel:
            dct.set_relation_from(dct_rel.name, doc.entities[i])

    # TODO: also convert to JSON for runtime-agnostic compatibility


def generate_dot(doc: Document) -> None:
    output = """digraph G {
    newrank=true;
    rankdir="LR"; ranksep=.75;
    node [shape=box,style=filled,fontname=Helvetica]
    """
    groups: Dict[str, List[Entity]] = {}
    for ent in doc.entities:
        if ent.tag == "TIMEX3" and ent.rels_from.keys():
            if set(ent.rels_from.keys()).issubset(set(Relation.time_rels)):
                continue
        groups.setdefault(ent.tag, []).append(ent)

    for tagtype, ents in groups.items():
        rank = "same"
        cluster = "subgraph "
        if tagtype == "Disease":
            rank = "source"
            # cluster = "subgraph clusterD "
        elif tagtype in [
            "Remedy",
            "TestVal",
            "MedicineVal",
            "ClinicalContext",
            "Pending",
        ]:
            rank = "max"
        for ent in ents:
            label = _make_dot_label(ent)
            output += f'T{ent.id}  [label="{label}",fillcolor="{CLR[ent.tag]}"];\n'
        output += (
            f"{cluster}{{ rank = {rank}; ordering=out;"
            + "; ".join([f"T{e.id}" for e in ents])
            + "; }\n"
        )

    for rel in doc.relations:
        if rel.name in rel.basic_rels:
            output += f'T{rel.arg1} -> T{rel.arg2} [label="{rel.name}"];\n'

    output += "}\n"
    print(output)


# def generate_table(doc: Document) -> None:
#     for ent in doc.entities:
#         if ent.tag.startswith("Medicine"):
#             pass


def _make_dot_label(ent: Entity) -> str:
    attr = ""
    if ent.attrs:
        if "certainty" in ent.attrs:
            cert = ent.attrs["certainty"].value
            if cert == "positive":
                attr = "(+)"
            elif cert == "negative":
                attr = "(-)"
            else:
                attr = "(?)"
        elif "state" in ent.attrs:
            state = ent.attrs["state"].value
            if state == "executed":
                attr = "(+)"
            elif state == "negated":
                attr = "(-)"
            else:
                attr = "(?)"

    if ent.tag != "TIMEX3":
        label = f"{ent.tag[0]}{attr}[{ent.text}]"
    else:
        label = f"<{ent.text}>"

    return label


def _generate_dot_from_raw(doc: Document, basic_only: bool = True) -> None:
    # Just for test purpose
    # init
    output = """digraph G {
            rankdir="LR";
            node [shape=box,style=filled,fontname=Helvetica]
    """

    # entity definitions
    for ent in doc.entities:
        label = _make_dot_label(ent)
        if ent.tag != "TIMEX3":
            output += (
                f'        T{ent.id} [label="{label}",fillcolor="{CLR[ent.tag]}"];\n'
            )
        else:
            output += (
                f"        T{ent.id} "
                f'[label="{label}",'
                'shape="plaintext",fillcolor="orchid"];\n'
            )

    # relations
    for rel in doc.relations:
        if basic_only and (rel.name not in rel.basic_rels):
            continue
        else:
            if rel.name in rel.basic_rels:
                output += f'        T{rel.arg1} -> T{rel.arg2} [label="{rel.name}"];\n'
            elif rel.name in rel.time_rels:
                output += (
                    f"        T{rel.arg1} -> T{rel.arg2} "
                    f'[label="{rel.name}",'
                    'color="magenta",fontcolor="magenta"];\n'
                )
            else:
                continue

    output += "}\n"
    print(output)


def main(filename_r: str) -> None:  # , tree: bool = False , table: bool = False
    # if tree and table:
    #     raise ValueError("--tree XOR --table")

    doc = Document(filename_r)

    # if tree:
    #     _generate_dot_from_raw(doc, basic_only=False)
    generate_dot(doc)

    # if table:
    #     generate_table(doc)


if __name__ == "__main__":
    fire.Fire(main)
