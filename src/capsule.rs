use crate::value::Value;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ProblemSeverity {
    Error,
    Warning,
}

impl ProblemSeverity {
    pub fn as_str(&self) -> &'static str {
        match self {
            ProblemSeverity::Error => "error",
            ProblemSeverity::Warning => "warning",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Problem {
    pub severity: ProblemSeverity,
    pub code: String,
    pub path: String,
    pub message: String,
}

impl Problem {
    pub fn error(
        code: impl Into<String>,
        path: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self {
            severity: ProblemSeverity::Error,
            code: code.into(),
            path: path.into(),
            message: message.into(),
        }
    }

    pub fn warning(
        code: impl Into<String>,
        path: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self {
            severity: ProblemSeverity::Warning,
            code: code.into(),
            path: path.into(),
            message: message.into(),
        }
    }

    pub fn to_value(&self) -> Value {
        Value::object(vec![
            ("severity", Value::from(self.severity.as_str())),
            ("code", Value::from(self.code.clone())),
            ("path", Value::from(self.path.clone())),
            ("message", Value::from(self.message.clone())),
        ])
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ExecutionStatus {
    Accepted,
    Rejected,
}

impl ExecutionStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            ExecutionStatus::Accepted => "accepted",
            ExecutionStatus::Rejected => "rejected",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExecutionOutput {
    pub status: ExecutionStatus,
    pub problems: Vec<Problem>,
    pub data: Value,
}

impl ExecutionOutput {
    pub fn new(status: ExecutionStatus, problems: Vec<Problem>, data: Value) -> Self {
        Self {
            status,
            problems,
            data,
        }
    }

    pub fn accepted(data: Value) -> Self {
        Self::new(ExecutionStatus::Accepted, Vec::new(), data)
    }

    pub fn has_errors(&self) -> bool {
        self.problems
            .iter()
            .any(|problem| matches!(problem.severity, ProblemSeverity::Error))
    }

    pub fn to_value(&self) -> Value {
        Value::object(vec![
            ("status", Value::from(self.status.as_str())),
            (
                "problems",
                Value::array(self.problems.iter().map(Problem::to_value).collect()),
            ),
            ("data", self.data.clone()),
        ])
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Manifest {
    pub id: String,
    pub name: String,
    pub version: String,
    pub profile: String,
    pub summary: String,
    pub logic_version: String,
    pub tags: Vec<String>,
    pub input_schema: SchemaNode,
    pub output_schema: SchemaNode,
}

impl Manifest {
    pub fn to_value(&self) -> Value {
        Value::object(vec![
            ("id", Value::from(self.id.clone())),
            ("name", Value::from(self.name.clone())),
            ("version", Value::from(self.version.clone())),
            ("profile", Value::from(self.profile.clone())),
            ("summary", Value::from(self.summary.clone())),
            ("logic_version", Value::from(self.logic_version.clone())),
            (
                "tags",
                Value::array(self.tags.iter().cloned().map(Value::from).collect()),
            ),
            ("input_schema", self.input_schema.to_value()),
            ("output_schema", self.output_schema.to_value()),
        ])
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct FieldSpec {
    pub name: String,
    pub required: bool,
    pub description: String,
    pub schema: SchemaNode,
}

impl FieldSpec {
    pub fn required(
        name: impl Into<String>,
        description: impl Into<String>,
        schema: SchemaNode,
    ) -> Self {
        Self {
            name: name.into(),
            required: true,
            description: description.into(),
            schema,
        }
    }

    pub fn optional(
        name: impl Into<String>,
        description: impl Into<String>,
        schema: SchemaNode,
    ) -> Self {
        Self {
            name: name.into(),
            required: false,
            description: description.into(),
            schema,
        }
    }

    pub fn to_value(&self) -> Value {
        Value::object(vec![
            ("name", Value::from(self.name.clone())),
            ("required", Value::from(self.required)),
            ("description", Value::from(self.description.clone())),
            ("schema", self.schema.to_value()),
        ])
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum SchemaNode {
    Any {
        description: String,
    },
    String {
        description: String,
    },
    Number {
        description: String,
        min: Option<f64>,
        max: Option<f64>,
    },
    Boolean {
        description: String,
    },
    Enum {
        description: String,
        values: Vec<String>,
    },
    Array {
        description: String,
        items: Box<SchemaNode>,
        min_items: Option<usize>,
    },
    Object {
        description: String,
        fields: Vec<FieldSpec>,
        allow_extra: bool,
    },
}

impl SchemaNode {
    pub fn any(description: impl Into<String>) -> Self {
        Self::Any {
            description: description.into(),
        }
    }

    pub fn string(description: impl Into<String>) -> Self {
        Self::String {
            description: description.into(),
        }
    }

    pub fn boolean(description: impl Into<String>) -> Self {
        Self::Boolean {
            description: description.into(),
        }
    }

    pub fn number(description: impl Into<String>, min: Option<f64>, max: Option<f64>) -> Self {
        Self::Number {
            description: description.into(),
            min,
            max,
        }
    }

    pub fn enumeration(description: impl Into<String>, values: Vec<&str>) -> Self {
        Self::Enum {
            description: description.into(),
            values: values.into_iter().map(str::to_string).collect(),
        }
    }

    pub fn array(
        description: impl Into<String>,
        items: SchemaNode,
        min_items: Option<usize>,
    ) -> Self {
        Self::Array {
            description: description.into(),
            items: Box::new(items),
            min_items,
        }
    }

    pub fn object(
        description: impl Into<String>,
        fields: Vec<FieldSpec>,
        allow_extra: bool,
    ) -> Self {
        Self::Object {
            description: description.into(),
            fields,
            allow_extra,
        }
    }

    pub fn to_value(&self) -> Value {
        match self {
            SchemaNode::Any { description } => Value::object(vec![
                ("type", Value::from("any")),
                ("description", Value::from(description.clone())),
            ]),
            SchemaNode::String { description } => Value::object(vec![
                ("type", Value::from("string")),
                ("description", Value::from(description.clone())),
            ]),
            SchemaNode::Number {
                description,
                min,
                max,
            } => Value::object(vec![
                ("type", Value::from("number")),
                ("description", Value::from(description.clone())),
                ("min", min.map(Value::from).unwrap_or(Value::Null)),
                ("max", max.map(Value::from).unwrap_or(Value::Null)),
            ]),
            SchemaNode::Boolean { description } => Value::object(vec![
                ("type", Value::from("boolean")),
                ("description", Value::from(description.clone())),
            ]),
            SchemaNode::Enum {
                description,
                values,
            } => Value::object(vec![
                ("type", Value::from("enum")),
                ("description", Value::from(description.clone())),
                (
                    "values",
                    Value::array(values.iter().cloned().map(Value::from).collect()),
                ),
            ]),
            SchemaNode::Array {
                description,
                items,
                min_items,
            } => Value::object(vec![
                ("type", Value::from("array")),
                ("description", Value::from(description.clone())),
                ("items", items.to_value()),
                (
                    "min_items",
                    min_items.map(Value::from).unwrap_or(Value::Null),
                ),
            ]),
            SchemaNode::Object {
                description,
                fields,
                allow_extra,
            } => Value::object(vec![
                ("type", Value::from("object")),
                ("description", Value::from(description.clone())),
                ("allow_extra", Value::from(*allow_extra)),
                (
                    "fields",
                    Value::array(fields.iter().map(FieldSpec::to_value).collect()),
                ),
            ]),
        }
    }

    pub fn validate(&self, value: &Value, path: &str, problems: &mut Vec<Problem>) {
        match self {
            SchemaNode::Any { .. } => {}
            SchemaNode::String { .. } => {
                if value.as_str().is_none() {
                    problems.push(Problem::error(
                        "invalid_type",
                        path.to_string(),
                        format!("Expected string, got {}", value.kind()),
                    ));
                }
            }
            SchemaNode::Number { min, max, .. } => match value.as_f64() {
                Some(number) => {
                    if let Some(minimum) = min {
                        if number < *minimum {
                            problems.push(Problem::error(
                                "number_below_minimum",
                                path.to_string(),
                                format!("Expected number >= {}, got {}", minimum, number),
                            ));
                        }
                    }
                    if let Some(maximum) = max {
                        if number > *maximum {
                            problems.push(Problem::error(
                                "number_above_maximum",
                                path.to_string(),
                                format!("Expected number <= {}, got {}", maximum, number),
                            ));
                        }
                    }
                }
                None => problems.push(Problem::error(
                    "invalid_type",
                    path.to_string(),
                    format!("Expected number, got {}", value.kind()),
                )),
            },
            SchemaNode::Boolean { .. } => {
                if value.as_bool().is_none() {
                    problems.push(Problem::error(
                        "invalid_type",
                        path.to_string(),
                        format!("Expected boolean, got {}", value.kind()),
                    ));
                }
            }
            SchemaNode::Enum { values, .. } => match value.as_str() {
                Some(text) => {
                    if !values.iter().any(|allowed| allowed == text) {
                        problems.push(Problem::error(
                            "invalid_enum_value",
                            path.to_string(),
                            format!("Unsupported value '{}'", text),
                        ));
                    }
                }
                None => problems.push(Problem::error(
                    "invalid_type",
                    path.to_string(),
                    format!("Expected enum string, got {}", value.kind()),
                )),
            },
            SchemaNode::Array {
                items, min_items, ..
            } => match value.as_array() {
                Some(values) => {
                    if let Some(minimum) = min_items {
                        if values.len() < *minimum {
                            problems.push(Problem::error(
                                "array_too_small",
                                path.to_string(),
                                format!("Expected at least {} item(s)", minimum),
                            ));
                        }
                    }
                    for (index, item) in values.iter().enumerate() {
                        let item_path = format!("{}[{}]", path, index);
                        items.validate(item, &item_path, problems);
                    }
                }
                None => problems.push(Problem::error(
                    "invalid_type",
                    path.to_string(),
                    format!("Expected array, got {}", value.kind()),
                )),
            },
            SchemaNode::Object {
                fields,
                allow_extra,
                ..
            } => match value.as_object() {
                Some(values) => {
                    for field in fields {
                        match values.get(field.name.as_str()) {
                            Some(field_value) => {
                                let field_path = join_path(path, &field.name);
                                field.schema.validate(field_value, &field_path, problems);
                            }
                            None if field.required => problems.push(Problem::error(
                                "missing_field",
                                join_path(path, &field.name),
                                format!("Missing required field '{}'", field.name),
                            )),
                            None => {}
                        }
                    }

                    if !allow_extra {
                        for key in values.keys() {
                            if !fields.iter().any(|field| field.name == *key) {
                                problems.push(Problem::error(
                                    "unexpected_field",
                                    join_path(path, key),
                                    format!("Unexpected field '{}'", key),
                                ));
                            }
                        }
                    }
                }
                None => problems.push(Problem::error(
                    "invalid_type",
                    path.to_string(),
                    format!("Expected object, got {}", value.kind()),
                )),
            },
        }
    }
}

fn join_path(base: &str, field: &str) -> String {
    if base.is_empty() {
        field.to_string()
    } else {
        format!("{base}.{field}")
    }
}

pub trait Capsule: Sync {
    fn id(&self) -> &'static str;
    fn manifest(&self) -> Manifest;
    fn execute(&self, input: &Value) -> ExecutionOutput;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_schema_missing_required_field() {
        let schema = SchemaNode::object(
            "root",
            vec![FieldSpec::required(
                "name",
                "Name",
                SchemaNode::string("Name"),
            )],
            false,
        );

        let value = Value::object(Vec::<(String, Value)>::new());
        let mut problems = Vec::new();
        schema.validate(&value, "", &mut problems);

        assert_eq!(problems.len(), 1);
        assert_eq!(problems[0].code, "missing_field");
    }
}
