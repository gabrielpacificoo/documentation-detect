# Documentação de dependências Spring Boot

Ferramenta Python que identifica microsserviços chamados por Feign, tabelas acessadas
por JPA/JDBC/SQL e chamadas a procedures do banco. Analisa somente `src/main` dos
módulos Java e gera `<nome-do-repositorio>.json` na raiz **deste projeto**.

## Executar

Requer Python 3.11 ou superior e Git instalado.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python getResource.py https://github.com/organizacao/servico.git
```

Sem URL, usa `https://github.com/Projeto-de-extencao-Grupo-3/back-end`, o laboratório
configurado originalmente. Também é possível executar pelo pacote:

```bash
python -m documentation_detect https://github.com/organizacao/servico.git --profile prod --branch main
```

Em **toda execução**, a ferramenta exclui `resource/` e clona novamente o repositório.
Essa pasta é descartável: alterações locais nela são removidas. A exclusão é
restrita a essa pasta, dentro deste projeto. A clonagem usa a branch padrão do remoto,
a menos que `--branch` seja informado. A autenticação é a do Git da máquina.

O fluxo é: substituir clone → ler `src/main` → executar detectores → gravar JSON.
Não exige banco de dados nem inicialização da aplicação Java. Uma falha de clonagem
ou leitura retorna código 1 e mantém o relatório anterior, caso exista.

## Saída

Exemplo ilustrativo de `servico.json`:

```json
{
  "servico": "servico",
  "microsservicos": ["clientes-api", "pagamentos-api"],
  "tabelas": ["clientes", "pedidos"],
  "procedures": ["PINS_PEDIDO", "PSEL_CLIENTES"]
}
```

As listas são ordenadas e não repetem nomes idênticos. Tabelas e procedures não
incluem schema; a grafia encontrada é preservada. Categorias sem resultados são `[]`.
O relatório é substituído por completo, sem acumular resultados de execuções antigas.

## Organização

```text
getResource.py                    # Entrada para execução
documentation_detect/
  cli.py                          # Argumentos e fluxo de execução
  repository.py                   # Exclusão controlada e nova clonagem
  source.py                       # Descoberta de arquivos em src/main
  java.py                         # Anotações, strings, constantes e comentários Java
  configuration.py                # Configuração Spring e resolução de placeholders
  sql.py                          # Contrato SqlAnalyzer e implementação MySQL
  models.py                       # Contexto, resultados e contrato Detector
  analyzer.py                     # Orquestração dos detectores
  detectors/
    procedures.py                 # Chamadas a procedures no banco
    microservices.py              # Dependências por @FeignClient
    tables.py                     # Mapeamentos JPA e consultas SQL
  report.py                       # Escrita do JSON
tests/                            # Casos de análise e integração com Git local
```

Cada detector recebe `AnalysisContext` e adiciona os nomes encontrados a `Findings`.
Novos detectores são registrados em `detectors.default_detectors()`. As regras de
uma categoria podem mudar sem alterar clonagem, leitura ou escrita do relatório.

### Procedures

- Considera os prefixos `PSEL`, `PDEL`, `PUPD` e `PINS`, sem diferenciar maiúsculas
  e minúsculas na identificação do prefixo.
- Identifica `CALL`, inclusive em strings JDBC como `{call PSEL_CLIENTES(?)}`,
  `SimpleJdbcCall.withProcedureName`, `createStoredProcedureQuery`,
  `createStoredProcedureCall`, `@Procedure` e `@NamedStoredProcedureQuery`.
- `@Procedure(name="alias")` referencia um mapeamento JPA: o nome real vem do
  `procedureName` de `@NamedStoredProcedureQuery`. O alias não é registrado como procedure.
- O nome `PSEL_CLIENTES.sql` **não** entra em `procedures`. Se seu conteúdo tem
  `SELECT ... FROM clientes`, registra `clientes` em `tabelas`. Se o conteúdo
  realmente executa `CALL PSEL_NO_BANCO()`, essa chamada entra em `procedures`.
- Comentários e simples menções a nomes de procedures não são chamadas.

### Tabelas

- JPA: `@Table`, `@SecondaryTable`, `@JoinTable` e `@CollectionTable`.
- Para `@Entity` sem nome explícito de tabela, infere o nome em `snake_case`,
  seguindo a convenção usual de Spring Boot. Estratégias de nomenclatura
  personalizadas e herança JPA podem exigir regras adicionais.
- JDBC: SQL literal, text blocks e concatenação de strings/constantes resolvíveis
  estaticamente. Inclui `SELECT`, `INSERT`, `REPLACE`, `UPDATE` e `DELETE`.
- Arquivos `.sql` em `src/main`, independentemente do nome do arquivo.
- Queries nativas JPA são SQL; `@Query` sem `nativeQuery=true` e `@NamedQuery`
  são ignoradas como SQL para não confundir entidades JPQL com tabelas.
- Usa a árvore SQL para identificar tabelas em joins, subconsultas e CTEs,
  sem listar o alias de uma CTE como tabela física. Ignora instruções DDL.

### Microsserviços e configuração

Lê `@FeignClient(name=..., value=..., url=...)` e arquivos
`application.properties`, `application.yml` e `application.yaml` do mesmo módulo.
Resolve referências `${chave}`, valores padrão `${VAR:valor}` e referências encadeadas.

A identificação segue esta ordem:

1. `name`/`value` resolvido de uma propriedade ou de seu valor padrão.
2. Host da URL resolvida, sem protocolo, porta, caminho ou credenciais.
3. `name`/`value` literal declarado na anotação.
4. Nome da interface/classe anotada.

URLs de `localhost`, endereços IP e `host.docker.internal` não identificam o nome do
serviço; nesses casos aplica o próximo fallback. Hosts DNS são preservados por inteiro.

Por padrão usa a configuração base e os perfis de `spring.profiles.active` ou
`spring.profiles.default`, quando resolvíveis; na ausência deles usa o perfil `default`.
`--profile prod` substitui essa seleção; vários perfis podem ser separados por vírgula.
Arquivos do perfil complementam/sobrescrevem a base. No mesmo diretório, properties
prevalece sobre YAML. Documentos YAML com `spring.config.activate.on-profile` também
são considerados para perfis simples ou separados por vírgula.

Não lê variáveis do ambiente da máquina que executa o analisador: sem um valor
presente no repositório, usa o default `${VAR:...}` ou o fallback da anotação.
Não acessa Config Server, secrets externos, imports de configuração ou expressões
complexas de ativação de perfil. Isso evita misturar a configuração da ferramenta
com a configuração do serviço analisado.

## Escopo e limites

- Exclui testes, build, `target`, diretórios gerados e links simbólicos.
- Faz inventário estático das declarações e SQLs em `src/main`; não comprova
  execução em runtime nem constrói um grafo de chamadas. Arquivos SQL em `src/main`
  são analisados mesmo que sua leitura pelo Java não possa ser comprovada.
- SQL montado dinamicamente com variáveis, reflexão, mapeamentos XML e estratégias
  JPA personalizadas não têm cobertura completa. JPQL fora das anotações, como queries
  passadas diretamente a `EntityManager.createQuery`, pode precisar de adaptação.
- SQL inválido ou não suportado gera aviso e não interrompe as outras detecções.
- O dialeto disponível é **MySQL**. DB2 está previsto pelo contrato `SqlAnalyzer`:
  implementar outro analisador em `sql.py`, registrá-lo em `create_sql_analyzer`
  e adicionar a opção na CLI. Não há suporte completo a DB2 nesta versão.

O parser SQL usa [SQLGlot](https://sqlglot.com/sqlglot.html), e a leitura YAML usa
`safe_load_all` do [PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation).

## Testes

```bash
python -m unittest discover -s tests -v
```

Os testes usam arquivos e repositórios Git temporários, sem acessar rede ou banco.
Cobrem Feign, perfis, placeholders, JPA, JDBC, SQL local, procedures, exclusões,
contrato JSON e atualização do clone após um novo commit no remoto local.
# documentation-detect
