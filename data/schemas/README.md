Vacío a propósito. El contrato del `RuleSet` vive en
`simulation/competitions/ruleset.py` como modelos de Pydantic, que es la única
fuente de verdad. Exportar el JSON Schema desde ahí es un comando
(`RuleSet.model_json_schema()`), no un archivo que haya que mantener a mano.
