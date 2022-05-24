import xml.etree.ElementTree as ET
from pathlib import Path

import fire
import pandas as pd
from tqdm import tqdm

# pd.set_option("display.max_colwidth", None)
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.unicode.ambiguous_as_wide", True)
pd.set_option("display.max_rows", None)
# pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", 15)

TAGNAMES = {
    "d": "Disease",
    "a": "Anatomical",
    "f": "Feature",
    "c": "Change",
    "timex3": "TIMEX3",
    "t-test": "TestTest",
    "t-key": "TestKey",
    "t-val": "TestVal",
    "m-key": "MedicineKey",
    "m-val": "MedicineVal",
    "cc": "ClinicalContext",
    "r": "Remedy",
    "p": "Pending",
}

# TODO: Relation!


def len_null(a):
    """Return length of the input even if it is None (=> 0)."""
    return 0 if a is None else len(a)


def get_plain_text(root):
    """Get a plain, bare text of an XML-tagged text."""
    return "".join(root.itertext()).lstrip()


def root_to_df(root, plain_text):
    """Convert an XML object to Table."""
    data = []
    data_r = []
    # NOTE: assume that non-PRISM tags don't appear between <root>...<[first PRISM tag]>
    root.text = root.text.lstrip() if root.text else None
    root.tail = None
    csr = len(root.text) if root.text else 0
    for e in root.iter():
        if e.tag.lower() in TAGNAMES:
            st, ed = csr, csr + len(e.text) if e.text else csr
            orig_snip = plain_text[st:ed]
            tag_datum = [
                e.tag,
                e.attrib,
                e.text,
                e.tail,
                st,
                ed,
                repr(orig_snip),
                e.text == orig_snip,
            ]
            if "tid" in e.attrib:
                tag_datum.insert(0, int(e.attrib["tid"][1:]))
                del e.attrib["tid"]
            data.append(tag_datum)
            csr += len_null(e.text) + len_null(e.tail)
        if e.tag == "brel":
            data_r.append(
                [
                    int(e.attrib["rid"][1:]),
                    e.attrib["reltype"],
                    int(e.attrib["arg1"][1:]),
                    int(e.attrib["arg2"][1:]),
                ]
            )
        # else:
        #     # some unknown tags exist
        #     # TODO: to make this procedure robust
    header = [
        "tag",
        "attrib",
        "text",
        "tail",
        "start_pos",
        "end_pos",
        "orig",
        "matchOrig",
    ]
    if len(header) + 1 == len(data[0]):
        header.insert(0, "tid")
    df = pd.DataFrame(data, columns=header)
    assert df["matchOrig"].all(), "\n" + str(df)
    header_r = ["rid", "reltype", "arg1", "arg2"]
    df_r = pd.DataFrame(data_r, columns=header_r)
    return df, df_r


def row_to_tagstr(row):
    """Convert a Table row to ANN's Tag format"""
    id_ = row.tid if "tid" in row else row.name
    if "\n" not in row.text:  # assume #\n == 1 (more than that is illegal)
        return f"T{id_}\t{TAGNAMES[row.tag.lower()]} {row.start_pos} {row.end_pos}\t{row.text}"
    n_pos = row.text.find("\n")
    fend_pos = row.start_pos + n_pos
    sstart_pos = fend_pos + 1
    text_ = row.text.replace("\n", " ")
    return f"T{id_}\t{TAGNAMES[row.tag.lower()]} {row.start_pos} {fend_pos};{sstart_pos} {row.end_pos}\t{text_}"


def df_to_tagstrs(df):
    """Convert all entities in a whole Table to ANN-formatted strings."""
    return df.apply(
        row_to_tagstr,
        axis=1,
    ).to_list()


def row_to_attrstr(row):
    """Convert a Table row to ANN's Attribute format"""
    id_ = row.tid if "tid" in row else row["index"]
    key, val = list(row.attrib.items())[0]
    return f"A{row.name + 1}\t{key} T{id_} {val}"


def df_to_attrstrs(df):
    """Convert all attribute info in a whole Table to ANN-formatted strings."""
    return (
        df[df.attrib != {}]
        .reset_index()  # to generate attr IDs
        .apply(
            row_to_attrstr,
            axis=1,
        )
        .to_list()
    )


def row_to_relstr(row):
    """Convert a Table row to ANN's Relation format"""
    return f"R{row.rid}\t{row.reltype} Arg1:T{row.arg1} Arg2:T{row.arg2}"


def df_to_relstrs(df_r):
    """Convert all relations to ANN-formatted strings."""
    return df_r.apply(row_to_relstr, axis=1).to_list()


def get_first_child(elem):
    """Get the first child of an XML Element"""
    it = elem.iter()
    next(it)  # == elem itself
    return next(it)


def get_real_root(elem):
    """Get the 'real' root element.
    This returns the direct parent that contains the PRISM tags.
    """
    child = get_first_child(elem)
    return elem if child.tag.lower() in TAGNAMES.keys() else get_real_root(child)


def main(dirpath, output_path, trav=False):
    """MAIN."""
    p = Path(dirpath)
    assert p.is_dir()
    p_lst = list(p.iterdir())
    outp = Path(output_path)
    if not outp.exists():
        outp.mkdir()
    for i in tqdm(p_lst):
        if i.name.startswith("."):
            continue
        if i.is_file() and i.suffix == ".xml":
            try:
                root = ET.parse(i).getroot()
                # if wrapped further by metadata elements like PERSON, ARTICLE
                # need to find the real "root"
                root = get_real_root(root)
            except ET.ParseError:
                with open(i, "r") as f:
                    cont = f.read()
                try:
                    root = ET.fromstring(f"<root>{cont}</root>")
                except ET.ParseError as e:
                    print()
                    print()
                    print("Error occured in:", i)
                    raise e
            plain_text = get_plain_text(root)
            try:
                df, df_r = root_to_df(root, plain_text)
            except AssertionError as e:
                print()
                print()
                print("Error occured in:", i)
                raise e
            tagstrs = df_to_tagstrs(df)
            attrstrs = df_to_attrstrs(df)
            relstrs = df_to_relstrs(df_r)
            with open(outp / i.with_suffix(".ann").name, "w") as outf:
                outf.write("\n".join(tagstrs + attrstrs + relstrs))
            with open(outp / i.with_suffix(".txt").name, "w") as outf:
                outf.write(plain_text)
        if i.is_dir() and trav:
            print("Dig into a child folder:", str(i))
            main(str(i), output_path)


if __name__ == "__main__":
    fire.Fire(main)
    # NOTE: only compatible with the 1-doc-per-file format
