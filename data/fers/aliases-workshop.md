# Workshop document option -> FER id mapping

Every checkbox option text extracted from `PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx` (the pt-BR workshop questionnaire, 5 area profiles), deduplicated, mapped to the FER `id` it should resolve to via `data/fers/seed.json` label/alias matching. Rows marked `unmatched: generic` are placeholder/non-substantive options ("Outro", "Ainda não definido", "Não se aplica", generic institutional or narrative phrases with no single canonical resource) and are expected to NOT resolve.

| Document option text (pt-BR) | Resolves to |
|---|---|
| A licença ou condição de uso ainda não foi definida | unmatched: generic |
| A vinculação ocorre apenas por links manuais | unmatched: generic |
| ABCD | https://abcd.tdwg.org/ |
| ABCD / BioCASe | https://abcd.tdwg.org/, https://www.biocase.org/ |
| AGROVOC | https://agrovoc.fao.org/ |
| API REST | unmatched: generic |
| Acesso apenas mediante solicitação formal | unmatched: generic |
| Acesso controlado mediante termo/acordo | unmatched: generic |
| Acesso controlado por DAC / DUA / Termo de Uso | unmatched: generic |
| Acesso público sem autenticação | unmatched: generic |
| Ainda não definido | unmatched: generic |
| Ainda não são utilizados vocabulários controlados | unmatched: generic |
| Ainda não é utilizado esquema formal | unmatched: generic |
| Ainda não é utilizado modelo ou padrão formal | unmatched: generic |
| Ambiente seguro / acesso remoto sem download | unmatched: generic |
| Ambiente seguro de análise | unmatched: generic |
| Ambiente seguro ou acesso remoto controlado | unmatched: generic |
| Apenas autoria e data são registradas | unmatched: generic |
| Apenas formato proprietário | unmatched: generic |
| Apenas os principais métodos são documentados | unmatched: generic |
| Apenas palavras-chave livres | unmatched: generic |
| Apenas texto não estruturado | unmatched: generic |
| Aprovação por Comitê de Acesso a Dados (DAC) | unmatched: generic |
| Aprovação por comitê ou instância responsável | unmatched: generic |
| Armazenamento em nuvem ou objetos | unmatched: generic |
| Autenticação federada e/ou multifator | unmatched: generic |
| BAM / CRAM para alinhamentos | https://samtools.github.io/hts-specs/CRAMv3.pdf, https://samtools.github.io/hts-specs/SAMv1.pdf |
| Backups, checksums e controle de versões | unmatched: generic |
| BioProject | https://www.ncbi.nlm.nih.gov/bioproject/ |
| BioProject–BioSample–Experiment–Run | https://www.ncbi.nlm.nih.gov/bioproject/ |
| BioSample / SRA / ENA accession | https://www.ebi.ac.uk/ena/browser/home, https://www.ncbi.nlm.nih.gov/biosample/, https://www.ncbi.nlm.nih.gov/sra |
| BrAPI (quando aplicável) | https://brapi.org/ |
| CC BY 4.0 | https://creativecommons.org/licenses/by/4.0/ |
| CC BY-NC 4.0 | https://creativecommons.org/licenses/by-nc/4.0/ |
| CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ |
| CSV / TSV | https://www.rfc-editor.org/rfc/rfc4180 |
| CSV tabular com dicionário de dados | https://www.rfc-editor.org/rfc/rfc4180 |
| CSV/TSV acompanhado de esquema | https://www.rfc-editor.org/rfc/rfc4180 |
| Campos de autoria e contribuição do DataCite | https://schema.datacite.org/ |
| Catálogo institucional | unmatched: generic |
| Catálogo ou índice da área | unmatched: generic |
| Catálogo taxonômico reconhecido | https://www.catalogueoflife.org/ |
| ChEBI | https://www.ebi.ac.uk/chebi/ |
| ChEBI / HMDB | https://hmdb.ca/, https://www.ebi.ac.uk/chebi/ |
| Chave de API | unmatched: generic |
| Checksums e relação entre entradas e saídas | unmatched: generic |
| Conta do repositório | unmatched: generic |
| Conta do repositório / institucional | unmatched: generic |
| Conta do repositório ou institucional | unmatched: generic |
| Conta institucional ou autenticação federada | unmatched: generic |
| Crop Ontology | https://www.cropontology.org/ |
| DDI | https://ddialliance.org/ |
| DDI (inquéritos e microdados) | https://ddialliance.org/ |
| DDI (quando pesquisa por questionário) | https://ddialliance.org/ |
| DDI para microdados | https://ddialliance.org/ |
| DDI para questionários | https://ddialliance.org/ |
| DOI | https://www.doi.org/ |
| DOI do conjunto de dados | https://www.doi.org/ |
| Darwin Core | https://dwc.tdwg.org/ |
| Darwin Core / DwC-A | https://dwc.tdwg.org/, https://dwc.tdwg.org/text/ |
| Darwin Core Archive (DwC-A) | https://dwc.tdwg.org/text/ |
| Darwin Core terms | https://dwc.tdwg.org/ |
| Darwin Core terms / TDWG vocabularies | https://dwc.tdwg.org/ |
| Data Use Ontology (DUO) | https://github.com/EBISPOT/DUO |
| DataCite | https://schema.datacite.org/ |
| DataCite / Bioschemas | https://bioschemas.org/, https://schema.datacite.org/ |
| DataCite Commons | https://commons.datacite.org/ |
| DataCite Commons / Google Dataset Search | https://commons.datacite.org/, https://datasetsearch.research.google.com/ |
| DataCite Commons ou Google Dataset Search | https://commons.datacite.org/, https://datasetsearch.research.google.com/ |
| DataCite Metadata Schema | https://schema.datacite.org/ |
| Dataverse ou Zenodo | https://dataverse.org/, https://zenodo.org/ |
| DeCS / MeSH | https://decs.bvsalud.org/, https://id.nlm.nih.gov/mesh/ |
| Dicionário de dados, métodos e protocolos | unmatched: generic |
| Dublin Core | https://purl.org/dc/terms/ |
| DwC Event para amostragem | https://dwc.tdwg.org/ |
| EGA / dbGaP | https://ega-archive.org/, https://www.ncbi.nlm.nih.gov/gap/ |
| EGA / dbGaP accession | https://ega-archive.org/, https://www.ncbi.nlm.nih.gov/gap/ |
| EML | https://eml.ecoinformatics.org/ |
| ENVO | https://obofoundry.org/ontology/envo |
| Ecological Metadata Language (EML) | https://eml.ecoinformatics.org/ |
| Environment Ontology (ENVO) | https://obofoundry.org/ontology/envo |
| Esquema do repositório ômico utilizado | unmatched: generic |
| Esquema próprio com dicionário de dados | unmatched: generic |
| Existem apenas rotinas de backup | unmatched: generic |
| FAIR Data Point | https://www.fairdatapoint.org/ |
| FASTA / FASTQ para sequências | https://en.wikipedia.org/wiki/FASTQ_format, https://www.ncbi.nlm.nih.gov/genbank/fastaformat/ |
| FASTQ / BAM / CRAM | https://en.wikipedia.org/wiki/FASTQ_format, https://samtools.github.io/hts-specs/CRAMv3.pdf, https://samtools.github.io/hts-specs/SAMv1.pdf |
| FTP/SFTP | https://www.rfc-editor.org/rfc/rfc959 |
| Formato proprietário acompanhado de exportação aberta | unmatched: generic |
| Formato proprietário acompanhado de formato aberto | unmatched: generic |
| GBIF Backbone / Catalogue of Life | https://www.catalogueoflife.org/, https://www.gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c |
| GBIF vocabularies | https://www.gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c |
| GEO / BioStudies | https://www.ebi.ac.uk/biostudies/, https://www.ncbi.nlm.nih.gov/geo/ |
| GEO accession | https://www.ncbi.nlm.nih.gov/geo/ |
| Gene Ontology / Sequence Ontology | https://geneontology.org/, https://obofoundry.org/ontology/so |
| GeoJSON | https://geojson.org/ |
| GeoJSON / GeoPackage | https://geojson.org/, https://www.geopackage.org/ |
| GeoJSON / padrões geoespaciais | https://geojson.org/ |
| GeoPackage / GeoJSON | https://www.geopackage.org/ |
| GeoTIFF | https://www.ogc.org/standard/geotiff/ |
| Git / controle de versões | https://git-scm.com/ |
| Git ou outro controle de versões | https://git-scm.com/ |
| Git ou sistema equivalente | https://git-scm.com/ |
| Google Dataset Search | https://datasetsearch.research.google.com/ |
| H5AD / AnnData | https://anndata.readthedocs.io/ |
| H5AD para célula única | https://anndata.readthedocs.io/ |
| HGNC / NCBI Gene / Ensembl | https://www.ensembl.org/ |
| HL7 FHIR | https://www.hl7.org/fhir/ |
| HL7 FHIR (quando dados clínicos/assistenciais) | https://www.hl7.org/fhir/ |
| HPO / Mondo | https://hpo.jax.org/, https://mondo.monarchinitiative.org/ |
| HTTPS | https://www.rfc-editor.org/rfc/rfc9110 |
| Handle ou ARK | https://arks.org/, https://www.handle.net/ |
| Histórico de versões e datas de atualização | unmatched: generic |
| Humboldt Extension | https://eco.tdwg.org/ |
| ICD-11 | https://icd.who.int/en |
| ICNP / SNOMED CT | https://www.icn.ch/how-we-do-it/projects/ehealth-icnp, https://www.snomed.org/ |
| ICNP integrada ao SNOMED CT | https://www.icn.ch/how-we-do-it/projects/ehealth-icnp, https://www.snomed.org/ |
| ISA | https://isa-tools.org/format/specification.html |
| ISA-Tab / ISA-JSON | https://isa-tools.org/format/specification.html |
| ISA-Tab / ISA-JSON para integração multiômica | https://isa-tools.org/format/specification.html |
| ISO 19115 | https://www.iso.org/standard/53798.html |
| ISO 19115 (dados geoespaciais) | https://www.iso.org/standard/53798.html |
| Identificador institucional persistente | unmatched: generic |
| Identificador persistente do repositório ou infraestrutura temática | unmatched: generic |
| Identificador/accession do repositório temático | unmatched: generic |
| Interface web sem API | unmatched: generic |
| JSON | https://www.json.org/json-en.html |
| JSON / FHIR | https://www.hl7.org/fhir/ |
| JSON / RDF | https://www.w3.org/TR/json-ld11/, https://www.w3.org/TR/rdf11-concepts/ |
| JSON Schema | https://json-schema.org/ |
| JSON-LD / RDF | https://www.w3.org/TR/json-ld11/, https://www.w3.org/TR/rdf11-concepts/ |
| JSON-LD ou RDF | https://www.w3.org/TR/json-ld11/, https://www.w3.org/TR/rdf11-concepts/ |
| LOINC | https://loinc.org/ |
| Licença institucional | unmatched: generic |
| Licença ou termos adotados pelo repositório | unmatched: generic |
| Licença ou termos do repositório | unmatched: generic |
| MIAME / MINSEQE / MIAPE | https://www.fged.org/projects/minseqe/, https://www.fged.org/projects/miame, https://www.psidev.info/miape |
| MIAPPE | https://www.miappe.org/ |
| MIAPPE (fenotipagem vegetal) | https://www.miappe.org/ |
| MIxS | https://genomicsstandardsconsortium.github.io/mixs/ |
| MIxS (incluindo MIGS/MIMS/MIMARKS) | https://genomicsstandardsconsortium.github.io/mixs/ |
| Manifesto, tabela de relacionamento ou dicionário de dados | unmatched: generic |
| MetaboLights / Metabolomics Workbench | https://www.ebi.ac.uk/metabolights/ |
| Metadados públicos sem licença explicitamente declarada | unmatched: generic |
| Migração de formatos | unmatched: generic |
| NCBI / ENA APIs | https://www.ebi.ac.uk/ena/browser/home |
| NCBI / GEO / ENA | https://www.ebi.ac.uk/ena/browser/home, https://www.ncbi.nlm.nih.gov/geo/ |
| NCBI Taxonomy | https://www.ncbi.nlm.nih.gov/taxonomy |
| NetCDF | https://www.unidata.ucar.edu/software/netcdf/ |
| NetCDF-CF para séries ambientais | https://cfconventions.org/ |
| Não se aplica | unmatched: generic |
| O registro detalhado ainda está em desenvolvimento | unmatched: generic |
| OAI-PMH | https://www.openarchives.org/pmh/ |
| OAuth 2.0 ou OpenID Connect | https://openid.net/specs/openid-connect-core-1_0.html, https://www.rfc-editor.org/rfc/rfc6749 |
| OBI / EFO | https://obofoundry.org/ontology/obi, https://www.ebi.ac.uk/efo/ |
| OMOP Common Data Model | https://ohdsi.github.io/CommonDataModel/ |
| ORCID e ROR | https://orcid.org/, https://ror.org/ |
| OmicsDI | https://www.omicsdi.org/ |
| Os dados ainda não estão acessíveis externamente | unmatched: generic |
| Outro | unmatched: generic |
| PRIDE / MetaboLights | https://www.ebi.ac.uk/metabolights/, https://www.ebi.ac.uk/pride/ |
| PRIDE / MetaboLights accession | https://www.ebi.ac.uk/metabolights/, https://www.ebi.ac.uk/pride/ |
| PRIDE / ProteomeXchange | http://www.proteomexchange.org/, https://www.ebi.ac.uk/pride/ |
| Parquet | https://parquet.apache.org/ |
| Perfil próprio documentado | unmatched: generic |
| Plano de Gestão de Dados ou política institucional | unmatched: generic |
| Plano de recuperação de desastres | unmatched: generic |
| Plant Ontology | https://browser.planteome.org/amigo |
| Política do repositório | unmatched: generic |
| Protocolo experimental e métricas de qualidade | unmatched: generic |
| Página DOI / DataCite relatedIdentifier | https://schema.datacite.org/meta/kernel-4.6/ |
| Página de destino associada ao DOI ou PID | https://schema.datacite.org/meta/kernel-4.6/ |
| RDF / JSON-LD | https://www.w3.org/TR/json-ld11/, https://www.w3.org/TR/rdf11-concepts/ |
| RDF / grafo de conhecimento | https://www.w3.org/TR/rdf11-concepts/ |
| RO-Crate | https://www.researchobject.org/ro-crate/ |
| RO-Crate / RDF / JSON-LD | https://www.researchobject.org/ro-crate/ |
| RO-Crate, RDF ou JSON-LD | https://www.researchobject.org/ro-crate/ |
| Referências cruzadas do repositório | unmatched: generic |
| Referências cruzadas entre repositórios | unmatched: generic |
| Relações BioProject–BioSample–experimento/execução | https://www.ncbi.nlm.nih.gov/bioproject/ |
| Relações ISA entre investigação, estudo, ensaio, amostra e arquivo | https://isa-tools.org/format/specification.html |
| Relações relatedIdentifier do DataCite | https://schema.datacite.org/meta/kernel-4.6/ |
| Repositório institucional | unmatched: generic |
| Repositório temático da área | unmatched: generic |
| Representação específica da área | unmatched: generic |
| Responsáveis definidos pela preservação | unmatched: generic |
| Reutilização não permitida | unmatched: generic |
| SNOMED CT | https://www.snomed.org/ |
| SPARQL | https://www.w3.org/TR/sparql11-protocol/ |
| SRA / ENA / DDBJ | https://www.ebi.ac.uk/ena/browser/home, https://www.ncbi.nlm.nih.gov/sra |
| SRA Toolkit / ferramentas ENA | https://github.com/ncbi/sra-tools |
| Sistema Internacional de Unidades (SI) | https://www.bipm.org/en/measurement-units |
| Sistema Internacional de Unidades / UCUM | https://ucum.org/ |
| Termo de Uso / DUA / consentimento compatível | unmatched: generic |
| Termo de uso / Data Use Agreement | unmatched: generic |
| Termos do repositório temático | unmatched: generic |
| UniProt | https://www.uniprot.org/ |
| Uso apenas em ambiente seguro | unmatched: generic |
| Uso compatível com consentimento e aprovação ética | unmatched: generic |
| Uso limitado à finalidade aprovada | unmatched: generic |
| VCF / BCF / gVCF | https://samtools.github.io/hts-specs/VCFv4.3.pdf |
| VCF / BCF para variantes | https://samtools.github.io/hts-specs/VCFv4.3.pdf |
| Versões de software, genoma de referência e parâmetros | unmatched: generic |
| Versões de software, parâmetros e configurações | unmatched: generic |
| Vocabulário institucional documentado | unmatched: generic |
| Vocabulário próprio documentado | unmatched: generic |
| W3C PROV / PROV-O | https://www.w3.org/TR/prov-o/ |
| W3C PROV / RO-Crate | https://www.researchobject.org/ro-crate/, https://www.w3.org/TR/prov-o/ |
| WoRMS (quando marinho) | https://www.marinespecies.org/ |
| Workflow, scripts ou notebooks | unmatched: generic |
| XML | https://www.w3.org/TR/xml/ |
| mzML / mzTab | https://www.psidev.info/mzml |
| mzML / mzTab para proteômica ou metabolômica | https://www.psidev.info/mzml |

**Totals:** 213 unique options; 137 resolve to a FER id; 76 are generic/placeholder (expected non-matches); 0 unresolved (needs review).
