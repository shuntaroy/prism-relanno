import re
import shutil
from pathlib import Path

import pandas as pd
from fire import Fire

PTN_ARG = re.compile(r"Arg\d:T(\d+)")


def main(brat_j, brat_e, jaen_match):
    pbe = Path(brat_e)
    pbm = Path(jaen_match)

    df_jaen = pd.read_csv(jaen_match)
    # NOTE: columns == ['index', 'tag', 'text', 'index.1', 'tag.1', 'text.1']
    jaen_maps = df_jaen[["index", "index.1"]].to_dict(orient="records")
    id_map = {d["index"]: d["index.1"] for d in jaen_maps}

    rels_to_map = []
    with open(brat_j, "r") as bj:
        for line in bj:
            if line.strip().startswith("R"):
                id_, reldata = line.strip().split("\t")
                rtype, arg1, arg2 = reldata.split(" ")
                mapped_arg1 = id_map[int(PTN_ARG.search(arg1).group(1))]
                mapped_arg2 = id_map[int(PTN_ARG.search(arg2).group(1))]
                rels_to_map.append(
                    f"{id_}\t{rtype} Arg1:T{mapped_arg1} Arg2:T{mapped_arg2}\n"
                )

    with open(brat_e, "r") as be:
        lines = [line for line in be if not line.startswith("R")]

    lines.extend(rels_to_map)

    pbe_trns = pbm.parent / pbe.name.replace(".ann", "-trns.ann")
    pte_trns = pbe_trns.with_suffix(".txt")
    with open(pbe_trns, "w") as of:
        of.writelines(lines)
    pte = pbe.with_suffix(".txt")
    shutil.copyfile(pte, pte_trns)


def renamedcopy(from_dirp, to_dirp):
    p = Path(from_dirp)
    pt = Path(to_dirp)
    for i in p.iterdir():
        if i.suffix in [".txt", ".ann"]:
            ri = i.stem.split("_")[0] + i.suffix
            shutil.copy(i, pt / ri)
        else:
            shutil.copy(i, pt / i.name)


if __name__ == "__main__":
    Fire(main)
