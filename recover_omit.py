"""Recover omit relations from an annotated result.

original.ann -> recovered.ann
"""
import sys
import fire
from typing import List

from entity_types import Entity, Relation, Attribute, Other, Id, findby_id

# TODO: クラス変更に応じて全面的に修正 (特にupdate部分)

# NOTE: Be aware that entity IDs start with 1
ENTITIES: List[Entity] = []
RELATIONS: List[Relation] = []
ATTRIBUTES: List[Attribute] = []
OTHERS: List[Other] = []


def read_ann_line(line: str) -> None:
    if line.startswith("T"):
        ENTITIES.append(Entity.from_raw(line))
    elif line.startswith("A"):
        ATTRIBUTES.append(Attribute.from_raw(line))
    elif line.startswith("R"):
        RELATIONS.append(Relation.from_raw(line))
    else:
        OTHERS.append(Other.from_raw(line))


# def add_relation(subj_id: Id, tgt_id: Id, rel_name: str) -> None:
#     entities[i].rels.setdefault("on", []).append(on_scope)
#     RELATIONS.append(
#         Relation(
#             _id=Id(len(RELATIONS) + 1),
#             name="on",
#             arg1=entities[i].id,
#             arg2=[e for e in entities if e.id == on_scope][0].id,
#         )
#     )


def recover_on(entities: List[Entity]) -> None:
    """Recover 'on'-relationship.

    Assume `entities` are sorted by the occurence order.
    """
    n = len(entities)
    # instead of list-based, use an index-based loop just in case for data corruption
    # 同格onの復元
    # TODO: test required
    # for i in range(n):
    #     if entities[i].rels.get("on") is not None:
    #         if getattr(entities[i], "DCT-Rel", None) == "on":
    #             for on_to in entities[i].rels["on"]:
    #                 setattr(findby_id(entities, on_to), "DCT-Rel", "on")
    #                 # NOTE: onではないDCT-Relが付与されていたらミスなので上書き
    #                 # FIXME: 既に存在するattributeがあったら削除が必要
    #                 ATTRIBUTES.append(
    #                     Attribute(
    #                         _id=Id(len(ATTRIBUTES) + 1),
    #                         name="DCT-Rel",
    #                         target=entities[i].id,
    #                         value="on",
    #                     )
    #                 )
    #         else:
    #             on_ids = entities[i].rels["on"]
    #             m = len(on_ids)
    #             for j, k in zip(range(m), range(1, m)):
    #                 e = findby_id(entities, on_ids[j])
    #                 if e.rels.get("on") is not None:
    #                     e.rels["on"].append(on_ids[k])
    #                 RELATIONS.append(
    #                     Relation(
    #                         _id=Id(len(RELATIONS) + 1),
    #                         name="on",
    #                         arg1=on_ids[j],
    #                         arg2=on_ids[k],
    #                     )
    #                 )

    # 省略onの復元
    on_scope: Id = Id(0)  # on省略の対象となるTIMEXのid
    for i in range(n):
        is_basic = entities[i].tag != "TIMEX3"

        if not is_basic:
            continue
        # after this line, always is_basic == True
        has_on = entities[i].rels.get("on") is not None
        has_on_dct = getattr(entities[i], "DCT-Rel", None) == "on"

        if on_scope == 0:  # initialise on_scope by the first case
            if has_on and (not has_on_dct):
                on_scope = entities[i].rels["on"][0]  # 同格が成立していればどれをとっても良い
            elif (not has_on) and has_on_dct:
                on_scope = Id(-1)  # the special value for DCT
            else:
                pass
            continue
        else:  # after initialisation
            # "直前のXがonするTime"をキープ
            if has_on and (not has_on_dct):
                on_scope = entities[i].rels["on"][0]  # 同格が成立していればどれをとっても良い
            elif (not has_on) and has_on_dct:
                on_scope = Id(-1)  # == DCT
            else:  # recover omit on
                has_time = any(
                    [
                        entities[i].rels.get(trel)
                        for trel in ["before", "after", "start", "finish"]
                    ]
                )
                if has_time:
                    continue
                # `on` is not needed if other time rels already assigned

                if on_scope != -1:
                    entities[i].rels.setdefault("on", []).append(on_scope)
                    RELATIONS.append(
                        Relation(
                            _id=Id(len(RELATIONS) + 1),
                            name="on",
                            arg1=entities[i].id,
                            arg2=[e for e in entities if e.id == on_scope][0].id,
                        )
                    )
                else:  # == -1 == DCT
                    setattr(entities[i], "DCT-Rel", "on")
                    ATTRIBUTES.append(
                        Attribute(
                            _id=Id(len(ATTRIBUTES) + 1),
                            name="DCT-Rel",
                            target=entities[i].id,
                            value="on",
                        )
                    )


def recover_value(entities: List[Entity]) -> None:
    """Recover 'value'-relationship.

    Explicitly draw 'value' relationships between key-value 1:1 occurences.
    Assume `entities` are sorted by the occurence order.
    """
    n = len(entities)
    # instead of list-based, use an index-based loop just in case for data corruption
    for i, j in zip(range(n), range(1, n)):
        i_is_key = entities[i].tag.endswith("Key")
        j_is_val = entities[j].tag == entities[i].tag.replace("Key", "Val")
        no_value = entities[j].id not in entities[i].rels.get("value", [])
        if i_is_key and j_is_val and no_value:
            entities[i].rels.setdefault("value", []).append(entities[j].id)
            RELATIONS.append(
                Relation(
                    _id=Id(len(RELATIONS) + 1),
                    name="value",
                    arg1=entities[i].id,
                    arg2=entities[j].id,
                )
            )


def output_ann(*annotations, fout=sys.stdout):
    for anno in annotations:
        for a in anno:
            if a is not None:
                print(a, file=fout)


def main(
    filename: str, on: bool = True, value: bool = True, write: bool = True
) -> None:
    with open(filename, "r") as fi:
        for line in fi:
            read_ann_line(line.strip())

    # update entities with attributes and relations
    for attr in ATTRIBUTES:
        setattr(findby_id(ENTITIES, attr.target), attr.name, attr.value)
        # NOTE: DCT-Rel is accessed via getattr() only
    for rel in RELATIONS:
        findby_id(ENTITIES, rel.arg1).rels.setdefault(rel.name, []).append(rel.arg2)

    entities = sorted(ENTITIES, key=lambda e: e.span[0])  # 出現順

    if on:
        recover_on(entities)

    if value:
        recover_value(entities)

    if write:
        with open(filename.replace(".ann", "-r.ann"), "w") as fout:
            output_ann(entities, RELATIONS, ATTRIBUTES, OTHERS, fout=fout)
    else:
        output_ann(entities, RELATIONS, ATTRIBUTES, OTHERS)


if __name__ == "__main__":
    fire.Fire(main)
    # activate an interactive session to debug
    # by adding `-- --interactive` at the end of exec command
