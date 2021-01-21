from pathlib import Path
import xml.etree.ElementTree as ET
import pandas as pd
import fire

TAGNAMES = {
    "d": "Disease",
    "a": "Anatomical",
    "f": "Feature",
    "c": "Change",
    "TIMEX3": "TIMEX3",
    "t-test": "TestTest",
    "t-key": "TestKey",
    "t-val": "TestVal",
    "m-key": "Medicinekey",
    "m-val": "MedicineVal",
    "cc": "ClinicalContext",
    "r": "Remedy",
    "p": "Pending",
}


def len_null(a):
    if a is None:
        return 0
    else:
        return len(a)


def get_plain_text(root):
    return "".join(root.itertext())


def root_to_df(root, plain_text):
    csr = 0
    data = []
    for e in root.iter():
        st, ed = csr, csr + len(e.text) if e.text else csr
        orig_snip = plain_text[st:ed]
        data.append(
            [
                e.tag,
                e.attrib,
                e.text,
                e.tail,
                st,
                ed,
                repr(orig_snip),
                e.text == orig_snip,
            ]
        )
        csr += len_null(e.text) + len_null(e.tail)
        df = pd.DataFrame(
            data,
            columns=[
                "tag",
                "attrib",
                "text",
                "tail",
                "start_pos",
                "end_pos",
                "orig",
                "matchOrig",
            ],
        )
    assert df.iloc[1:]["matchOrig"].all(), df
    return df


def row_to_tagstr(row):
    if "\n" in row.text:  # assume #\n == 1 (more than that is illegal)
        n_pos = row.text.find("\n")
        fend_pos = row.start_pos + n_pos
        sstart_pos = fend_pos + 1
        text_ = row.text.replace("\n", " ")
        return f"T{row.name}\t{TAGNAMES[row.tag]} {row.start_pos} {fend_pos};{sstart_pos} {row.end_pos}\t{text_}"
    else:
        return f"T{row.name}\t{TAGNAMES[row.tag]} {row.start_pos} {row.end_pos}\t{row.text}"


def df_to_tagstrs(df):
    return (
        df.iloc[1:]  # skip root
        .apply(
            row_to_tagstr,
            axis=1,
        )
        .to_list()
    )


def row_to_attrstr(row):
    key, val = list(row.attrib.items())[0]
    return f"A{row.name + 1}\t{key} T{row['index']} {val}"


def df_to_attrstrs(df):
    return (
        df[df.attrib != {}]
        .reset_index()  # to generate attr IDs
        .apply(
            row_to_attrstr,
            axis=1,
        )
        .to_list()
    )


def main(dirpath, output_path):
    p = Path(dirpath)
    outp = Path(output_path)
    for i in p.iterdir():
        if i.name.startswith("."):
            continue
        if i.is_file():
            try:
                root = ET.parse(i).getroot()
            except ET.ParseError:
                with open(i, "r") as f:
                    cont = f.read()
                root = ET.fromstring(f"<root>{cont}</root>")
            plain_text = get_plain_text(root)
            try:
                df = root_to_df(root, plain_text)
            except AssertionError as e:
                print(i)
                raise e
            tagstrs = df_to_tagstrs(df)
            attrstrs = df_to_attrstrs(df)
            with open(outp / i.with_suffix(".ann").name, "w") as outf:
                outf.write("\n".join(tagstrs + attrstrs))
            with open(outp / i.with_suffix(".txt").name, "w") as outf:
                outf.write(plain_text)
        if i.is_dir():
            main(str(i), output_path)


if __name__ == "__main__":
    fire.Fire(main)
