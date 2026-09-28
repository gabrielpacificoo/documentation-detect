import json
import tempfile
import unittest
from pathlib import Path

from documentation_detect.analyzer import analyze
from documentation_detect.configuration import Configuration, properties
from documentation_detect.report import write_report
from documentation_detect.sql import MysqlAnalyzer


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def java(self, content, name="Example.java", module=""):
        return self.write(f"{module + '/' if module else ''}src/main/java/{name}", content)

    def test_jpa_native_jpql_comments_and_implicit_names(self):
        self.java('''
            @Entity @Table(name="clientes", schema="lab") class Cliente {
                @JoinTable(name="cliente_perfil") Set<Perfil> perfis;
                @CollectionTable(name="telefones") Set<String> telefones;
            }
            @Entity class OrdemCompra {}
            // @Table(name="falsa")
            /* @Entity @Table(name="outra_falsa") class Inativa {} */
            interface Repository {
                @Query("SELECT c FROM Cliente c JOIN c.perfis p") Object list();
                @Query(value="SELECT * FROM lab.auditoria a JOIN usuarios u ON a.id=u.id", nativeQuery=true)
                Object nativeList();
            }
        ''')
        self.assertEqual(analyze(self.root).tabelas,
                         {"clientes", "cliente_perfil", "telefones", "ordem_compra", "auditoria", "usuarios"})

    def test_jdbc_literals_text_blocks_and_constants(self):
        self.java('''
            class Queries {
                static final String BASE = "SELECT * FROM estoque ";
                static final String SQL = BASE + "JOIN produtos p ON p.id = estoque.produto_id";
            }
        ''', "Queries.java")
        self.java('''
            class Access {
                void load() {
                    jdbcClient.sql(Queries.SQL).query();
                    jdbcTemplate.update("UPDATE clientes SET nome = ? WHERE id = ?", nome, id);
                    jdbc.sql("INSERT INTO pedidos (id) VALUES (:id)");
                    jdbc.sql("DELETE FROM itens WHERE id=?");
                    jdbc.sql("""
                        SELECT * FROM `lab`.`pagamentos`
                        WHERE status = :status
                    """);
                }
            }
        ''')
        self.assertEqual(analyze(self.root).tabelas,
                         {"estoque", "produtos", "clientes", "pedidos", "itens", "pagamentos"})

    def test_sql_file_named_like_procedure_is_only_a_table_access(self):
        self.write("src/main/resources/procedures/PSEL_CLIENTES.sql", '''
            -- CALL PSEL_COMENTADA(); SELECT * FROM falsa;
            SELECT * FROM lab.clientes c JOIN enderecos e ON e.cliente_id = c.id;
        ''')
        result = analyze(self.root)
        self.assertEqual(result.tabelas, {"clientes", "enderecos"})
        self.assertEqual(result.procedures, set())

    def test_jpql_constant_is_not_a_physical_table(self):
        self.java('''
            @Entity @Table(name="clientes") class Cliente {}
            interface Repository {
                String JPQL = "SELECT c FROM Cliente c";
                @Query(JPQL) Object list();
            }
        ''')
        self.assertEqual(analyze(self.root).tabelas, {"clientes"})

    def test_procedures_only_real_call_forms_with_expected_prefix(self):
        self.java('''
            @NamedStoredProcedureQuery(name="alias", procedureName="lab.PSEL_LISTAR")
            class Operations {
                static final String PROC = "PUPD_CLIENTE";
                void run() {
                    connection.prepareCall("{call lab.PSEL_CLIENTES(?)}");
                    connection.prepareCall("{? = call PSEL_CONTAR()}");
                    new SimpleJdbcCall(jdbc).withProcedureName(PROC);
                    em.createStoredProcedureQuery("PDEL_CLIENTE");
                    em.createStoredProcedureQuery("SEM_PREFIXO");
                    read("procedures/PSEL_LOCAL.sql");
                    String description = "PSEL_NAO_CHAMADA";
                    // connection.prepareCall("{call PSEL_COMENTADA()}");
                }
            }
            interface Repo {
                @Procedure(procedureName="PINS_CLIENTE") void insert();
                @Procedure("PDEL_ITEM") void delete();
                @Procedure(name="alias") void list();
                @Procedure void PUPD_TOTAL();
            }
        ''')
        self.write("src/main/resources/operations.sql", "CALL PSEL_INTERNA(); SELECT * FROM registros;")
        result = analyze(self.root)
        self.assertEqual(result.procedures, {"PSEL_LISTAR", "PSEL_CLIENTES", "PSEL_CONTAR", "PUPD_CLIENTE",
                                            "PDEL_CLIENTE", "PINS_CLIENTE", "PDEL_ITEM", "PUPD_TOTAL", "PSEL_INTERNA"})
        self.assertEqual(result.tabelas, {"registros"})

    def test_feign_configuration_urls_defaults_and_fallbacks(self):
        self.write("src/main/resources/application.yaml", '''
clients:
  orders:
    name: ${ORDERS_NAME:pedidos}
    url: http://orders-api:8080
  billing:
    url: ${BILLING_URL:http://billing-api:8080/v1}
''')
        self.java('''
            @FeignClient(name="${clients.orders.name}", url="${clients.orders.url}") interface Orders {}
            @FeignClient(name="internal", url="${clients.billing.url}") interface Billing {}
            @FeignClient(name="estoque", url="http://localhost:8080") interface Local {}
            @FeignClient(value="clientes", url="http://127.0.0.1:8080") interface Ip {}
            @FeignClient(name="fallback", url="${missing}") interface Missing {}
            @FeignClient(name="${unknown}", url="${missing}") interface ClassFallback {}
            @FeignClient("short-name") interface Short {}
            // @FeignClient("ignored") interface Ignored {}
        ''')
        self.assertEqual(analyze(self.root).microsservicos,
                         {"pedidos", "billing-api", "estoque", "clientes", "fallback", "ClassFallback", "short-name"})

    def test_profiles_properties_precedence_and_module_isolation(self):
        self.write("one/src/main/resources/application.yml", "api:\n  name: yaml-name\n")
        self.write("one/src/main/resources/application.properties",
                   "api.name=base\nspring.profiles.active=${PROFILE:dev}\n")
        self.write("one/src/main/resources/application-dev.properties", "api.name=development\n")
        self.write("one/src/main/resources/application-prod.properties", "api.name=production\n")
        self.write("two/src/main/resources/application.yaml", "api:\n  name: second-module\n")
        for module in ("one", "two"):
            self.java('@FeignClient(name="${api.name}") interface Api {}', module=module)
        self.assertEqual(analyze(self.root).microsservicos, {"development", "second-module"})
        self.assertEqual(analyze(self.root, profile="prod").microsservicos, {"production", "second-module"})

    def test_yaml_documents_are_profile_scoped(self):
        self.write("src/main/resources/application.yml", '''
api:
  name: base
---
spring:
  config:
    activate:
      on-profile: prod
api:
  name: production
''')
        self.java('@FeignClient(name="${api.name}") interface Api {}')
        self.assertEqual(analyze(self.root).microsservicos, {"base"})
        self.assertEqual(analyze(self.root, profile="prod").microsservicos, {"production"})

    def test_only_main_sources_and_no_symlinks(self):
        self.java('@Entity @Table(name="real") class Entity {}')
        for path in ("src/test/java/Fake.java", "target/src/main/java/Fake.java",
                     "build/src/main/resources/fake.sql", "README.sql"):
            self.write(path, 'SELECT * FROM fake;')
        outside = self.write("outside.sql", "SELECT * FROM outside;")
        link = self.root / "src/main/java/linked.sql"
        link.symlink_to(outside)
        self.assertEqual(analyze(self.root).tabelas, {"real"})

    def test_json_contract_and_deduplication(self):
        self.java('@Entity @Table(name="clientes") class Cliente {}')
        self.write("src/main/resources/list.sql", "SELECT * FROM clientes; SELECT * FROM pedidos;")
        output = write_report(analyze(self.root), "my-service", self.root)
        self.assertEqual(json.loads(output.read_text()), {
            "servico": "my-service", "microsservicos": [], "tabelas": ["clientes", "pedidos"], "procedures": []
        })
        self.assertEqual(list(self.root.glob(".report-*")), [])

    def test_empty_repository_is_an_error(self):
        with self.assertRaises(ValueError):
            analyze(self.root)


class SqlTests(unittest.TestCase):
    def setUp(self):
        self.sql = MysqlAnalyzer()

    def test_cte_subqueries_comma_joins_and_schema(self):
        query = '''
            WITH ativos AS (SELECT * FROM lab.clientes WHERE ativo=1)
            SELECT * FROM ativos a JOIN pedidos p ON p.cliente_id=a.id,
                fornecedores f WHERE p.id IN (SELECT pedido_id FROM itens)
        '''
        self.assertEqual(self.sql.tables(query), {"clientes", "pedidos", "fornecedores", "itens"})

    def test_writes_and_literals(self):
        self.assertEqual(self.sql.tables('''
            INSERT INTO resumo SELECT * FROM pedidos;
            UPDATE clientes c JOIN enderecos e ON c.id=e.cliente_id SET c.ativo=1;
            DELETE FROM itens WHERE pedido_id=?;
            SELECT 'FROM falsa; :literal' FROM configuracoes;
        '''), {"resumo", "pedidos", "clientes", "enderecos", "itens", "configuracoes"})

    def test_call_in_sql_literal_and_comments_is_not_a_procedure(self):
        self.assertEqual(self.sql.procedures("SELECT 'CALL PSEL_FALSA()' FROM t; -- CALL PDEL_FALSA()\n"), set())
        self.assertEqual(self.sql.procedures('CALL `lab`.`PSEL_REAL`(); call pins_registro();'),
                         {"PSEL_REAL", "pins_registro"})


    def test_mysql_delete_alias_and_replace(self):
        self.assertEqual(self.sql.tables("DELETE c FROM clientes c JOIN pedidos p ON p.cliente_id=c.id"),
                         {"clientes", "pedidos"})
        self.assertEqual(self.sql.tables("REPLACE INTO clientes (id) VALUES (?)"), {"clientes"})


class ConfigurationTests(unittest.TestCase):
    def test_nested_defaults_missing_values_and_cycles(self):
        config = Configuration({"a": "${b}", "b": "${a}", "host": "api"})
        self.assertIsNone(config.resolve("${a}"))
        self.assertIsNone(config.resolve("http://${missing}"))
        self.assertEqual(config.resolve("${URL:http://${host}:8080/v1}"), "http://api:8080/v1")

    def test_properties_colons_continuations_and_unicode(self):
        self.assertEqual(properties("""# comment
api.url: https://api.example.com:8443
api.name = cli\\u0065ntes
api.path=/api/\\
    v1
"""), {"api.url": "https://api.example.com:8443", "api.name": "clientes", "api.path": "/api/v1"})


if __name__ == "__main__":
    unittest.main()
