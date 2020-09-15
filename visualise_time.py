"""Visualise time containers from annotation."""
from typing import List, Dict, Set, Optional

import fire


from entity_types import Id, Document, Entity, Relation
import visualise_rel as vr
from visualise_rel import CLR, DOTHEAD

# TODO: merge visualise_rel.py with this code

# NOTE: relevant time expression parsers/rules are available in timex_modules/


class TimeContainer:
    def __init__(self):
        self.b_ents = set()
        self.t_ents = set()

    def add(self, ent: Entity) -> None:
        if ent.tag == "TIMEX3":
            self.t_ents.add(ent)
        else:
            self.b_ents.add(ent)

    def all_ents(self) -> Set[Entity]:
        return self.t_ents | self.b_ents

    def find_head_timex(self) -> None:
        # FIXME: precise handling of head TIMEX in a TC
        if self.t_ents:
            self.head = list(self.t_ents)[0]
        else:
            self.head = list(self.b_ents)[0]

    # TODO: define sortability


def make_time_containers(entities: List[Entity]) -> List[TimeContainer]:
    """
    time containers = timex clusters connected with 'on'

    - make absolute time expressions parent of time containers
    - order time containers chronologically
    """
    # recursively find the root → recursively find all on-related
    # TODO: manage entities that have before/start/... only (no 'on' =~ relative timex)
    time_containers: List[TimeContainer] = []
    while entities:
        ent = entities.pop(0)
        # debug = debugger.Pdb().set_trace()
        tc = TimeContainer()
        tc = make_tc_helper(ent, tc)
        tc.find_head_timex()  # not properly implemented yet
        time_containers.append(tc)
        entities = [entity for entity in entities if entity not in tc.all_ents()]

    # TODO: order/merge time containers chronologically
    return time_containers


def make_tc_helper(ent: Entity, tc: TimeContainer) -> TimeContainer:
    if ent not in tc.all_ents():
        tc.add(ent)
        froms = ent.rels_from.get("on", set())
        tos = ent.rels_to.get("on", set())
        rel_ents = froms | tos
        # while froms:
        while rel_ents:
            # tc = make_tc_helper(froms.pop(), tc)
            tc = make_tc_helper(rel_ents.pop(), tc)

    return tc


def generate_dot(doc: Document) -> str:
    """Draw a chronologically aligned dot graph."""
    # NOTE: 2020/09/11 modified for simple vis: timex-only clusters with timerels
    # output = DOTHEAD
    output = "digraph G {rankdir=LR; newrank=true; node [shape=box,style=filled,fontname=Helvetica]"
    entities = doc.entities
    # entities = [e for e in doc.entities if e.tag == "TIMEX3"]
    # ids = [e.id for e in entities]
    # Define all nodes first
    for ent in entities:
        if ent.id == Id(-1):
            ent.id = Id(10000)
        label = vr._make_dot_label(ent)
        output += f'T{ent.id}  [label="{label}",fillcolor="{CLR[ent.tag]}"];\n'
    for rel in doc.relations:
        if rel.name in rel.basic_rels:
            output += f'T{rel.arg1} -> T{rel.arg2} [label="{rel.name}"];\n'
        # if rel.arg1 in ids and rel.arg2 in ids:
        if rel.name in rel.time_rels and not rel.name.startswith("o"):
            if rel.arg1 == Id(-1):
                rel.arg1 = Id(10000)
            if rel.arg2 == Id(-1):
                rel.arg2 = Id(10000)
            output += f'T{rel.arg1} -> T{rel.arg2} [label="{rel.name}",color="magenta",fontcolor="magenta"];\n'

    # create time containers
    containers = make_time_containers([e for e in doc.entities if e.tag == "TIMEX3"])

    # define the timeline
    # FIXME: chronological ordering
    output += "{ "
    output += " -> ".join([f"T{container.head.id}" for container in containers])
    output += " [arrowhead=none] }\n"

    for ix, container in enumerate(containers):
        # TODO: 全部をrank=sameのsubgraphにするときっと一列になる
        # まずは rank constraint なしで time container を cluster subgraph として様子見
        # FIXME: container をまるっと可視化してるだけ
        output += (
            f"subgraph cluster{ix}{{ rank=same; ordering=out;"
            + "; ".join([f"T{e.id}" for e in container.all_ents()])
            # + "; ".join([f"T{e.id}" for e in container.t_ents])
            + "; }\n"
        )

    output += "}\n"
    return output


def generate_tsv(doc: Document) -> str:
    """Debug purpose."""
    containers = make_time_containers([e for e in doc.entities if e.tag == "TIMEX3"])
    table: List[List[str]] = []
    contained_ids: List[Id] = []
    for container in containers:
        contained_ids += [e.id for e in container.all_ents()]
        table.append(
            [repr(ent) for ent in list(container.t_ents) + list(container.b_ents)]
            # [repr(ent) for ent in container.t_ents]
        )
    # containerに入らなかったものをまとめる
    table.append(
        [repr(entity) for entity in doc.entities if entity.id not in contained_ids]
    )

    return "\n".join(["\t".join(row) for row in table])


def relate_dct(doc: Document) -> None:
    """Convert DCT-Rel to a Relation."""
    assert doc.isbuilt

    # create the DCT entity
    dct = Entity(Id(-1), "TIMEX3", (-2, -1), "DCT", doc=doc)
    doc.entities.insert(0, dct)

    n = len(doc.entities)
    for i in range(n):
        dct_rel = doc.entities[i].attrs.get("DCT-Rel")
        if dct_rel:
            doc.add_relation(dct_rel, doc.entities[i].id, dct.id)


def main(filename_r: str) -> None:
    doc = Document(filename_r)
    relate_dct(doc)
    print(generate_dot(doc))
    # print(generate_tsv(doc))


if __name__ == "__main__":
    fire.Fire(main)
