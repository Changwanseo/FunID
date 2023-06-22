from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq
import itertools
import logging
from functools import reduce
import pandas as pd
from copy import deepcopy
from funid.src import search, hasher
import numpy as np


def combine_alignment(V, opt, path):
    for group in V.dict_dataset:
        if "concatenated" in V.dict_dataset[group]:
            # get alignment length
            # length of each of the alignments
            len_dict = {}
            seq_dict = {}
            hash_set = set()
            gene_list = []

            for gene in V.dict_dataset[group]:
                if not (gene == "concatenated"):
                    fasta_list = list(
                        SeqIO.parse(
                            f"{path.out_alignment}/{opt.runname}_trimmed_{group}_{gene}.fasta",
                            "fasta",
                        )
                    )
                    len_dict[gene] = len(fasta_list[0].seq)
                    seq_dict[gene] = {}
                    total_dataset = (
                        [
                            FI.hash
                            for FI in V.dict_dataset[group]["concatenated"].list_qr_FI
                        ]
                        + [
                            FI.hash
                            for FI in V.dict_dataset[group]["concatenated"].list_db_FI
                        ]
                        + [
                            FI.hash
                            for FI in V.dict_dataset[group]["concatenated"].list_og_FI
                        ]
                    )
                    for seq in fasta_list:
                        if seq.description in total_dataset:  # if available hash
                            seq_dict[gene][seq.description] = seq
                            hash_set.add(seq.description)

            # Generate partition file
            with open(
                f"{path.out_alignment}/{opt.runname}_{group}.partition", "w"
            ) as fw:
                tot_len = 0
                for gene in sorted(len_dict.keys()):
                    gene_list.append(gene)
                    fw.write(f"DNA, {gene}= {tot_len+1}-{tot_len+len_dict[gene]}\n")
                    tot_len += len_dict[gene]

            # Generate concatenated alignment file
            concatenate_list = []
            for hash_id in hash_set:
                tmp_seq = ""
                for gene in gene_list:
                    if hash_id in seq_dict[gene]:
                        tmp_seq += str(seq_dict[gene][hash_id].seq)
                    else:
                        # add gaps for ids without gene
                        tmp_seq += "-" * len_dict[gene]

                concatenate_list.append(
                    SeqRecord(id=hash_id, description="", seq=Seq(tmp_seq))
                )

            SeqIO.write(
                concatenate_list,
                f"{path.out_alignment}/{opt.runname}_trimmed_{group}_concatenated.fasta",
                "fasta",
            )

        else:
            logging.warning(
                f"For {group}, no more than genes were detected. Passing combining alignment"
            )

    return V


# for concatenating blast result to get single bitscore among results
def concatenate_df(V, path, opt):
    logging.info("Concatenating search results")

    gene_list = []
    df_list = []
    for gene in V.dict_gene_SR.keys():
        # Leave non-empty dataframes
        if isinstance(V.dict_gene_SR[gene], pd.DataFrame):
            gene_list.append(gene)
            df = deepcopy(V.dict_gene_SR[gene].set_index(["qseqid", "sseqid"]))
            df_list.append(df)

    if len(df_list) <= 0:
        logging.warning(f"Stop concatenating because same or less than 0 gene exists")
        return V

    else:
        # drop unused columns
        cnt = 0

        # Change biscore names
        for n, df in enumerate(df_list):
            gene = gene_list[n]
            df[f"{gene}_bitscore"] = df["bitscore"]
            df[f"{gene}_subject_group"] = df["subject_group"]

        # Concatenate multiple dataframes
        df_multigene_regression_ori = pd.concat(df_list, axis=1)

        # Drop unnecessary columns
        df_multigene_regression_ori.drop(
            columns=[
                "pident",
                "length",
                "mismatch",
                "gaps",
                "qstart",
                "qend",
                "sstart",
                "send",
                "evalue",
                "bitscore",
                "subject_group",
            ],
            inplace=True,
        )

        # Work on subject_group
        def same_merge(x, list_col):
            values = x[list_col].dropna()
            if values.empty:
                raise Exception
            return values.iloc[0]

        df_multigene_regression_ori[
            "subject_group"
        ] = df_multigene_regression_ori.apply(
            lambda x: same_merge(x, [f"{gene}_subject_group" for gene in gene_list]),
            axis=1,
        )

        # For regression, leave genes with all genes existing
        df_multigene_regression = df_multigene_regression_ori

        for gene in gene_list:
            df_multigene_regression = df_multigene_regression[
                df_multigene_regression[f"{gene}_bitscore"].notna()
            ]

        # Count the number of entries. If not enough number exists, add terms with one NaN
        num = 0
        fail_flag = 0
        while len(df_multigene_regression) < 3:
            print(
                f"Failed to find enough normalization point with {len(gene_list)-num} genes."
            )
            num += 1
            df_multigene_regression_all = []
            if num < len(gene_list):
                for leave_genes in itertools.combinations(gene_list, num):
                    for gene in gene_list:
                        if not gene in leave_genes:
                            df_multigene_regression_all.append(
                                df_multigene_regression_ori[
                                    df_multigene_regression[f"{gene}_bitscore"].notna()
                                ]
                            )
                df_multigene_regression = pd.concat(df_multigene_regression_all)
            else:
                fail_flag = 1
                break

        df_multigene_regression.reset_index().to_excel("Test.xlsx", index=False)

        # Get normalization parameters for all genes
        norm_param_dict = {}
        for gene in gene_list:
            norm_param_dict[gene] = {}
            values = df_multigene_regression[f"{gene}_bitscore"][
                df_multigene_regression[f"{gene}_bitscore"].notna()
            ]
            norm_param_dict[gene]["mean"] = values.mean()
            norm_param_dict[gene]["std"] = values.std()

        # Return to original multigene, or normalize
        # multiply 100 to use with previous offset options
        for gene in gene_list:
            df_multigene_regression_ori[f"{gene}_bitscore"] = (
                (
                    df_multigene_regression_ori[f"{gene}_bitscore"]
                    - norm_param_dict[gene]["mean"]
                )
                / norm_param_dict[gene]["std"]
                * 100
            )

        # Get average from multigene matrix
        df_multigene_regression_ori["bitscore"] = df_multigene_regression_ori[
            [f"{gene}_bitscore" for gene in gene_list]
        ].mean(axis=1)

        V.cSR = df_multigene_regression_ori.reset_index()
        V.cSR.reset_index().to_excel("TestTest.xlsx", index=False)

        """

        while 1:
            if isinstance(df_list[cnt], pd.DataFrame):
                # If non-empty dataframe selected,
                if not (df_list[cnt].empty):
                    V.cSR = df_list[cnt]
                    V.cSR.drop(
                        columns=[
                            "pident",
                            "length",
                            "mismatch",
                            "gaps",
                            "qstart",
                            "qend",
                            "sstart",
                            "send",
                            "evalue",
                        ],
                        inplace=True,
                    )
                    cnt += 1
                    break
            cnt += 1

        # generate concatenated search result
        for df in df_list[cnt:]:
            if isinstance(df_list[cnt], pd.DataFrame):
                if not (df_list[cnt].empty):
                    df.drop(
                        columns=[
                            "pident",
                            "length",
                            "mismatch",
                            "gaps",
                            "qstart",
                            "qend",
                            "sstart",
                            "send",
                            "evalue",
                        ],
                        inplace=True,
                    )
                    V.cSR = pd.merge(
                        V.cSR,
                        df,
                        how="outer",
                        on=["sseqid", "qseqid"],
                        suffixes=("1", "2"),
                    )

                    drop_list = []
                    rename_dict = {}

                    # concatenate bitscore columns
                    if "bitscore1" in V.cSR.columns:
                        V.cSR["bitscore1"].fillna(value=0, inplace=True)
                        V.cSR["bitscore2"].fillna(value=0, inplace=True)
                        V.cSR["bitscore"] = V.cSR["bitscore1"] + V.cSR["bitscore2"]
                        drop_list.append("bitscore1")
                        drop_list.append("bitscore2")

                    # concatenate query group column
                    if "query_group1" in V.cSR.columns:
                        V.cSR["query_group1"].fillna(
                            V.cSR["query_group2"], inplace=True
                        )
                        rename_dict["query_group1"] = "query_group"
                        drop_list.append("query_group2")

                    # concatenate subject group column
                    if "subject_group1" in V.cSR.columns:
                        V.cSR["subject_group1"].fillna(
                            V.cSR["subject_group2"], inplace=True
                        )
                        rename_dict["subject_group1"] = "subject_group"
                        drop_list.append("subject_group2")

                    V.cSR.rename(columns=rename_dict, inplace=True)
                    V.cSR.drop(
                        columns=drop_list,
                        inplace=True,
                    )
    """

    # Save it
    # decode df is not working well here
    if opt.nosearchresult is False:
        search.save_df(
            hasher.decode_df(hash_dict=V.dict_id_hash, df=V.cSR),
            f"{path.out_matrix}/{opt.runname}_BLAST_result_concatenated.{opt.matrixformat}",
            fmt=opt.matrixformat,
        )

    return V
