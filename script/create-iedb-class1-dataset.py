#!/usr/bin/env python

# Copyright (c) 2016. Mount Sinai School of Medicine
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Turn a raw CSV snapshot of the IEDB contents into a usable
class I binding prediction dataset by grouping all unique pMHCs
"""
from collections import defaultdict
from os import makedirs
from os.path import join, exists
import pickle
import argparse

import numpy as np
import pandas as pd

from mhcflurry.paths import CLASS1_DATA_DIRECTORY


IEDB_SOURCE_FILENAME = "mhc_ligand_full.csv"
PICKLE_OUTPUT_FILENAME = "iedb_human_class1_assay_datasets.pickle"

parser = argparse.ArgumentParser()

parser.add_argument(
    "--input-csv",
    default=IEDB_SOURCE_FILENAME,
    help="CSV file with IEDB's MHC binding data")

parser.add_argument(
    "--output-dir",
    default=CLASS1_DATA_DIRECTORY,
    help="Directory to write output pickle file")


parser.add_argument(
    "--output-pickle-filename",
    default=PICKLE_OUTPUT_FILENAME,
    help="Path to .pickle file containing dictionary of IEDB assay datasets")

if __name__ == "__main__":
    args = parser.parse_args()
    df = pd.read_csv(
        args.input_csv,
        error_bad_lines=False,
        encoding="latin-1",
        header=[0, 1])
    alleles = df["MHC"]["Allele Name"]
    n = len(alleles)
    print("# total: %d" % n)

    mask = np.zeros(n, dtype=bool)
    patterns = [
        "HLA-A",
        "HLA-B",
        "HLA-C",
        "H-2",
    ]
    for pattern in patterns:
        pattern_mask = alleles.str.startswith(pattern)
        print("# %s: %d" % (pattern, pattern_mask.sum()))
        mask |= pattern_mask
    df = df[mask]
    print("# entries matching allele masks: %d" % (len(df)))
    assay_group = df["Assay"]["Assay Group"]
    assay_method = df["Assay"]["Method/Technique"]
    groups = df.groupby([assay_group, assay_method])
    print("---")
    print("Assays")
    assay_dataframes = {}
    # create a dataframe for every distinct kind of assay which is used
    # by IEDB submitters to measure peptide-MHC affinity or stability
    for (assay_group, assay_method), group_data in sorted(
            groups, key=lambda x: len(x[1]), reverse=True):
        print("%s (%s): %d" % (assay_group, assay_method, len(group_data)))
        group_alleles = group_data["MHC"]["Allele Name"]
        group_peptides = group_data["Epitope"]["Description"]
        distinct_pmhc = group_data.groupby([group_alleles, group_peptides])
        columns = defaultdict(list)
        for (allele, peptide), pmhc_group in distinct_pmhc:
            columns["mhc"].append(allele)
            columns["peptide"].append(peptide)
            # performing median in log space since in two datapoint case
            # we don't want to take e.g. (10 + 1000) / 2.0 = 505
            # but would prefer something like 10 ** ( (1 + 3) / 2.0) = 100
            columns["value"].append(
                np.exp(
                    np.median(
                        np.log(
                            pmhc_group["Assay"]["Quantitative measurement"]))))
            qualitative = pmhc_group["Assay"]["Qualitative Measure"]
            columns["percent_positive"].append(
                qualitative.str.startswith("Positive").mean())
            columns["count"].append(
                pmhc_group["Assay"]["Quantitative measurement"].count())
        assay_dataframes[(assay_group, assay_method)] = pd.DataFrame(
            columns,
            columns=[
                "mhc",
                "peptide",
                "value",
                "percent_positive",
                "count"])
        print("# distinct pMHC entries: %d" % len(columns["mhc"]))
    if not exists(args.output_dir):
        makedirs(args.output_dir)

    output_path = join(args.output_dir, args.output_pickle_filename)

    with open(args.output, "wb") as f:
        pickle.dump(assay_dataframes, f, pickle.HIGHEST_PROTOCOL)
