import xml.etree.ElementTree as ET
from pathlib import Path

import fire
import pandas as pd

import xml2brat as xb


def get_df(xml):
    root = ET.parse(xml)
    root = xb.get_real_root(root)
    text = xb.get_plain_text(root)
    return xb.root_to_df(root, text)


def main(xml_ja, xml_en):
    df_ja = get_df(xml_ja)
    g_ja = df_ja.groupby("tag")

    df_en = get_df(xml_en)
    g_en = df_en.groupby("tag")

    joints = []
    for name, g_e in g_en:
        g_j = g_ja.get_group(name).reset_index()
        assert len(g_j) == len(g_e)
        cols = ["index", "tag", "text"]
        joints.append(pd.concat([g_j[cols], g_e.reset_index()[cols]], axis=1))
    df_jaen = pd.concat(joints, ignore_index=True)

    p = Path(xml_ja)
    df_jaen.to_csv(p.stem + "-jaen_match.csv", index=False)


if __name__ == "__main__":
    fire.Fire(main)
