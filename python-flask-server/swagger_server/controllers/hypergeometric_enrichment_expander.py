from swagger_server.models.gene_info import GeneInfo
from swagger_server.models.transformer_info import TransformerInfo
from swagger_server.models.parameter import Parameter
from swagger_server.models.gene_info import GeneInfoIdentifiers
from swagger_server.models.attribute import Attribute

#REQUIREMENTS
import scipy.stats
from numpy import array, empty
import json
#available at http://software.broadinstitute.org/gsea/downloads.jsp
msigdb_gmt_files=['dat/c2.all.current.0.entrez.gmt', 'dat/c5.all.current.0.entrez.gmt']

#END REQUIREMENTS

transformer_name = 'MSigDB hypergeometric enrichment expander'
valid_controls = ['max p-value', 'max q-value']
control_names = {'max p-value': 'max p-value', 'max q-value': 'max q-value'}
default_control_values = {'max p-value': 1e-5, 'max q-value': 0.05}
default_control_types = {'max p-value': 'double', 'max q-value': 'double'}

def get_control(controls, control):
    value = controls[control_names[control]] if control_names[control] in controls else default_control_values[control]
    if default_control_types[control] == 'double':
        return float(value)
    elif default_control_types[control] == 'Boolean':
        return bool(value)
    elif default_control_types[control] == 'int':
        return int(value)
    else:
        return value

def entrez_gene_id(gene: GeneInfo):
    """
        Return value of the entrez_gene_id attribute
    """
    if (gene.identifiers is not None and gene.identifiers.entrez is not None):
        if (gene.identifiers.entrez.startswith('NCBIGene:')):
            return gene.identifiers.entrez[9:]
        else:
            return gene.identifiers.entrez
    return None

def correct_pvalues_for_multiple_testing(pvalues, correction_type = "Benjamini-Hochberg"):
    """
    consistent with R - print correct_pvalues_for_multiple_testing([0.0, 0.01, 0.029, 0.03, 0.031, 0.05, 0.069, 0.07, 0.071, 0.09, 0.1])
    """
    pvalues = array(pvalues)
    n = int(pvalues.shape[0])
    new_pvalues = empty(n)
    if correction_type == "Bonferroni":
        new_pvalues = n * pvalues
    elif correction_type == "Bonferroni-Holm":
        values = [ (pvalue, i) for i, pvalue in enumerate(pvalues) ]
        values.sort()
        for rank, vals in enumerate(values):
            pvalue, i = vals
            new_pvalues[i] = (n-rank) * pvalue
    elif correction_type == "Benjamini-Hochberg":
        values = [ (pvalue, i) for i, pvalue in enumerate(pvalues) ]
        values.sort()
        values.reverse()
        new_values = []
        for i, vals in enumerate(values):
            rank = n - i
            pvalue, index = vals
            new_values.append((n/rank) * pvalue)
        for i in range(0, int(n)-1):
            if new_values[i] < new_values[i+1]:
                new_values[i+1] = new_values[i]
        for i, vals in enumerate(values):
            pvalue, index = vals
            new_pvalues[index] = new_values[i]
    return new_pvalues

def expand(query):  # noqa: E501

    controls = {control.name:control.value for control in query.controls}
    #Add the originally input genes
    gene_list = query.genes
    genes = dict([(entrez_gene_id(gene) if entrez_gene_id(gene) != None else gene.gene_id, None) for gene in gene_list])

    #Read in the gene sets
    gene_set_y_gene_list_y = {}
    gene_set_y_gene_list_n = {}
    gene_set_n_gene_list_y = {}
    gene_set_n_gene_list_n = {}
    gene_set_k = {}
    gene_set_N = {}
    gene_set_gene_ids = {}
    all_gene_set_gene_ids = set()
    for msigdb_gmt_file in msigdb_gmt_files:
        msigdb_gmt_fh = open(msigdb_gmt_file)
        for line in msigdb_gmt_fh:
            cols = line.strip().split('\t')
            if len(cols) < 3:
                continue
            gene_set_id = cols[0]
            gene_ids = cols[2:len(cols)]
            overlap = len([x for x in gene_ids if x in genes])
            if overlap == 0:
                continue
            gene_set_y_gene_list_y[gene_set_id] = overlap
            gene_set_gene_ids[gene_set_id] = gene_ids
            gene_set_N[gene_set_id] = len(gene_ids)

            gene_set_y_gene_list_n[gene_set_id] = gene_set_N[gene_set_id] - gene_set_y_gene_list_y[gene_set_id]
            gene_set_n_gene_list_y[gene_set_id] = len(genes) - gene_set_y_gene_list_y[gene_set_id]
            for x in gene_ids:
                all_gene_set_gene_ids.add(x)
        msigdb_gmt_fh.close()
    M = len(all_gene_set_gene_ids)

    gene_set_pvalues = {}
    gene_set_qvalues = {}
    gene_set_odds_ratios = {}
    all_pvalues = []
    all_gene_set_ids = []

    for gene_set_id in gene_set_y_gene_list_y:
        gene_set_n_gene_list_n[gene_set_id] = M - gene_set_y_gene_list_y[gene_set_id] - gene_set_y_gene_list_n[gene_set_id] - gene_set_n_gene_list_y[gene_set_id]

        table = [[gene_set_y_gene_list_y[gene_set_id], gene_set_y_gene_list_n[gene_set_id]], [gene_set_n_gene_list_y[gene_set_id], gene_set_n_gene_list_n[gene_set_id]]]
        odds_ratio, pvalue = scipy.stats.fisher_exact(table)

        all_pvalues.append(pvalue)
        all_gene_set_ids.append(gene_set_id)

        if pvalue < get_control(controls, 'max p-value'):
            gene_set_pvalues[gene_set_id] = pvalue
            gene_set_odds_ratios[gene_set_id] = odds_ratio

    all_qvalues = correct_pvalues_for_multiple_testing(all_pvalues, correction_type="Benjamini-Hochberg")
    for i, gene_set_id in enumerate(all_gene_set_ids):
        if gene_set_id in gene_set_pvalues and all_qvalues[i] < get_control(controls, 'max q-value'):
            gene_set_qvalues[gene_set_id] = all_qvalues[i]

    for gene_set_id in sorted(gene_set_qvalues.keys(), key=lambda x: gene_set_qvalues[x]):
        for gene_id in gene_set_gene_ids[gene_set_id]:
            gene_entrez_id = "NCBIGene:%s" % gene_id
            if gene_entrez_id not in genes:
                genes[gene_entrez_id] = GeneInfo(
                    gene_id = gene_entrez_id,
                    identifiers = GeneInfoIdentifiers(entrez = gene_entrez_id),
                    attributes = [
                      Attribute(
                        name = 'gene set',
                        value = gene_set_id,
                        source = transformer_name,
                        url = 'http://software.broadinstitute.org/gsea/msigdb/cards/{}.html'.format(gene_set_id)
                      ),
                      Attribute(
                        name = 'p-value',
                        value = gene_set_pvalues[gene_set_id],
                        source = transformer_name
                      ),
                      Attribute(
                        name = 'q-value',
                        value = gene_set_qvalues[gene_set_id],
                        source = transformer_name
                      ),
                      Attribute(
                        name = 'odds ratio',
                        value = odds_ratio,
                        source = transformer_name
                      ),
                    ]
                  )
                gene_list.append(genes[gene_entrez_id])
    return gene_list


def expander_info():  # noqa: E501
    """Retrieve transformer info

    Provides information about the transformer. # noqa: E501


    :rtype: TransformerInfo
    """
    global transformer_name, control_names

    with open("transformer_info.json",'r') as f:
        info = TransformerInfo.from_dict(json.loads(f.read()))
        transformer_name = info.name
        control_names = dict((name,parameter.name) for name, parameter in zip(valid_controls, info.parameters))
        return info


