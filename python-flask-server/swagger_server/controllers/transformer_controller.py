import connexion
import six

from swagger_server.models.gene_info import GeneInfo  # noqa: E501
from swagger_server.models.transformer_info import TransformerInfo  # noqa: E501
from swagger_server.models.transformer_query import TransformerQuery  # noqa: E501
from swagger_server import util
from swagger_server.models.parameter import Parameter
from swagger_server.models.gene_info import GeneInfoIdentifiers
from swagger_server.models.attribute import Attribute

#REQUIREMENTS
import scipy.stats

msigdb_gmt_file='swagger_server/controllers/dat/c2.all.v7.0.entrez.gmt'

#END REQUIREMENTS

valid_controls = ['max p-value']
default_control_values = {'max p-value': 1e-5}
default_control_types = {'max p-value': 'double'}

def get_control(controls, control):
    value = controls[control] if control in controls else default_control_values[control]
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

def transform_post(query):  # noqa: E501
    """transform_post

     # noqa: E501

    :param query: Performs transformer query.
    :type query: dict | bytes

    :rtype: List[GeneInfo]
    """
    if connexion.request.is_json:
        query = TransformerQuery.from_dict(connexion.request.get_json())  # noqa: E501

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
    gene_set_odds_ratios = {}
    for gene_set_id in gene_set_y_gene_list_y:
        gene_set_n_gene_list_n[gene_set_id] = M - gene_set_y_gene_list_y[gene_set_id] - gene_set_y_gene_list_n[gene_set_id] - gene_set_n_gene_list_y[gene_set_id]

        table = [[gene_set_y_gene_list_y[gene_set_id], gene_set_y_gene_list_n[gene_set_id]], [gene_set_n_gene_list_y[gene_set_id], gene_set_n_gene_list_n[gene_set_id]]]
        odds_ratio, pvalue = scipy.stats.fisher_exact(table)

        if pvalue < get_control(controls, 'max p-value'):
            gene_set_pvalues[gene_set_id] = pvalue
            gene_set_odds_ratios[gene_set_id] = odds_ratio

    for gene_set_id in sorted(gene_set_pvalues.keys(), key=lambda x: gene_set_pvalues[x]):
        for gene_id in gene_set_gene_ids[gene_set_id]:
            if gene_id not in genes:
                gene_entrez_id = "NCBIGene:%s" % gene_id
                genes[gene_entrez_id] = GeneInfo(
                    gene_id = gene_entrez_id,
                    attributes = [
                      Attribute(
                        name = 'gene set',
                        value = gene_set_id,
                        source = 'Hypergeometric enrichment expander'
                      ),
                      Attribute(
                        name = 'p-value',
                        value = pvalue,
                        source = 'Hypergeometric enrichment expander'
                      ),
                      Attribute(
                        name = 'odds ratio',
                        value = odds_ratio,
                        source = 'Hypergeometric enrichment expander'
                      ),
                    ]
                  )
                gene_list.append(genes[gene_entrez_id])
    return gene_list


def transformer_info_get():  # noqa: E501
    """Retrieve transformer info

    Provides information about the transformer. # noqa: E501


    :rtype: TransformerInfo
    """
    return TransformerInfo(
        name = 'Hypergeometric gene set enrichment expander',
        function = 'expander',
        operation = 'enrichment',
        ui_label = 'HyperGeomEnrich',
        source_url = 'http://software.broadinstitute.org/gsea/downloads.jsp',
        description = 'Gene-list expander that adds all genes in pathways enriched for genes in the input',
        parameters = [Parameter(x, default_control_types[x], default_control_values[x]) for x in valid_controls],
        required_attributes = ['identifiers.entrez','gene_symbol']
    )

