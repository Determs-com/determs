use crate::value::Value;
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JsonError {
    pub message: String,
    pub position: usize,
}

impl JsonError {
    fn new(message: impl Into<String>, position: usize) -> Self {
        Self {
            message: message.into(),
            position,
        }
    }
}

impl core::fmt::Display for JsonError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "JSON error at byte {}: {}", self.position, self.message)
    }
}

pub fn parse(input: &str) -> Result<Value, JsonError> {
    let mut parser = Parser::new(input);
    let value = parser.parse_value()?;
    parser.skip_whitespace();
    if parser.peek().is_some() {
        return Err(JsonError::new(
            "Unexpected trailing characters",
            parser.position,
        ));
    }
    Ok(value)
}

pub fn to_canonical_string(value: &Value) -> String {
    let mut output = String::new();
    write_canonical(value, &mut output);
    output
}

pub fn to_pretty_string(value: &Value) -> String {
    let mut output = String::new();
    write_pretty(value, 0, &mut output);
    output
}

struct Parser<'a> {
    input: &'a str,
    bytes: &'a [u8],
    position: usize,
}

impl<'a> Parser<'a> {
    fn new(input: &'a str) -> Self {
        Self {
            input,
            bytes: input.as_bytes(),
            position: 0,
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.position).copied()
    }

    fn bump(&mut self) -> Option<u8> {
        let byte = self.peek()?;
        self.position += 1;
        Some(byte)
    }

    fn skip_whitespace(&mut self) {
        while let Some(byte) = self.peek() {
            if matches!(byte, b' ' | b'\n' | b'\r' | b'\t') {
                self.position += 1;
            } else {
                break;
            }
        }
    }

    fn parse_value(&mut self) -> Result<Value, JsonError> {
        self.skip_whitespace();
        match self.peek() {
            Some(b'n') => self.parse_null(),
            Some(b't') => self.parse_true(),
            Some(b'f') => self.parse_false(),
            Some(b'"') => self.parse_string().map(Value::String),
            Some(b'-' | b'0'..=b'9') => self.parse_number().map(Value::Number),
            Some(b'[') => self.parse_array(),
            Some(b'{') => self.parse_object(),
            Some(_) => Err(JsonError::new("Unexpected token", self.position)),
            None => Err(JsonError::new("Unexpected end of input", self.position)),
        }
    }

    fn parse_null(&mut self) -> Result<Value, JsonError> {
        self.expect_literal("null")?;
        Ok(Value::Null)
    }

    fn parse_true(&mut self) -> Result<Value, JsonError> {
        self.expect_literal("true")?;
        Ok(Value::Bool(true))
    }

    fn parse_false(&mut self) -> Result<Value, JsonError> {
        self.expect_literal("false")?;
        Ok(Value::Bool(false))
    }

    fn expect_literal(&mut self, literal: &str) -> Result<(), JsonError> {
        let start = self.position;
        for expected in literal.as_bytes() {
            match self.bump() {
                Some(byte) if byte == *expected => {}
                _ => return Err(JsonError::new(format!("Expected '{}'", literal), start)),
            }
        }
        Ok(())
    }

    fn parse_string(&mut self) -> Result<String, JsonError> {
        if self.bump() != Some(b'"') {
            return Err(JsonError::new("Expected string", self.position));
        }

        let mut output = String::new();
        while let Some(byte) = self.bump() {
            match byte {
                b'"' => return Ok(output),
                b'\\' => {
                    let escaped = self.bump().ok_or_else(|| {
                        JsonError::new("Unexpected end of input in escape sequence", self.position)
                    })?;
                    match escaped {
                        b'"' => output.push('"'),
                        b'\\' => output.push('\\'),
                        b'/' => output.push('/'),
                        b'b' => output.push('\u{0008}'),
                        b'f' => output.push('\u{000C}'),
                        b'n' => output.push('\n'),
                        b'r' => output.push('\r'),
                        b't' => output.push('\t'),
                        b'u' => {
                            let codepoint = self.parse_unicode_escape()?;
                            let character = char::from_u32(codepoint as u32).ok_or_else(|| {
                                JsonError::new("Invalid unicode escape", self.position)
                            })?;
                            output.push(character);
                        }
                        _ => {
                            return Err(JsonError::new(
                                "Unsupported escape sequence",
                                self.position.saturating_sub(1),
                            ));
                        }
                    }
                }
                0x00..=0x1F => {
                    return Err(JsonError::new(
                        "Control characters are not allowed in JSON strings",
                        self.position.saturating_sub(1),
                    ));
                }
                _ => output.push(byte as char),
            }
        }

        Err(JsonError::new("Unterminated string", self.position))
    }

    fn parse_unicode_escape(&mut self) -> Result<u16, JsonError> {
        let start = self.position;
        let slice = self
            .input
            .get(self.position..self.position + 4)
            .ok_or_else(|| JsonError::new("Incomplete unicode escape", start))?;
        self.position += 4;
        u16::from_str_radix(slice, 16).map_err(|_| JsonError::new("Invalid unicode escape", start))
    }

    fn parse_number(&mut self) -> Result<f64, JsonError> {
        let start = self.position;

        if self.peek() == Some(b'-') {
            self.position += 1;
        }

        match self.peek() {
            Some(b'0') => self.position += 1,
            Some(b'1'..=b'9') => {
                self.position += 1;
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.position += 1;
                }
            }
            _ => return Err(JsonError::new("Invalid number", start)),
        }

        if self.peek() == Some(b'.') {
            self.position += 1;
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(JsonError::new("Invalid decimal number", self.position));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.position += 1;
            }
        }

        if matches!(self.peek(), Some(b'e' | b'E')) {
            self.position += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.position += 1;
            }
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(JsonError::new("Invalid exponent", self.position));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.position += 1;
            }
        }

        self.input[start..self.position]
            .parse::<f64>()
            .map_err(|_| JsonError::new("Invalid number", start))
    }

    fn parse_array(&mut self) -> Result<Value, JsonError> {
        self.bump();
        self.skip_whitespace();

        let mut values = Vec::new();
        if self.peek() == Some(b']') {
            self.bump();
            return Ok(Value::Array(values));
        }

        loop {
            values.push(self.parse_value()?);
            self.skip_whitespace();
            match self.bump() {
                Some(b',') => {
                    self.skip_whitespace();
                }
                Some(b']') => break,
                _ => return Err(JsonError::new("Expected ',' or ']'", self.position)),
            }
        }

        Ok(Value::Array(values))
    }

    fn parse_object(&mut self) -> Result<Value, JsonError> {
        self.bump();
        self.skip_whitespace();

        let mut values = BTreeMap::new();
        if self.peek() == Some(b'}') {
            self.bump();
            return Ok(Value::Object(values));
        }

        loop {
            let key = self.parse_string()?;
            self.skip_whitespace();
            if self.bump() != Some(b':') {
                return Err(JsonError::new("Expected ':'", self.position));
            }
            self.skip_whitespace();
            let value = self.parse_value()?;
            values.insert(key, value);
            self.skip_whitespace();
            match self.bump() {
                Some(b',') => {
                    self.skip_whitespace();
                }
                Some(b'}') => break,
                _ => return Err(JsonError::new("Expected ',' or '}'", self.position)),
            }
        }

        Ok(Value::Object(values))
    }
}

fn write_canonical(value: &Value, output: &mut String) {
    match value {
        Value::Null => output.push_str("null"),
        Value::Bool(true) => output.push_str("true"),
        Value::Bool(false) => output.push_str("false"),
        Value::Number(number) => output.push_str(&number_to_string(*number)),
        Value::String(value) => write_string(value, output),
        Value::Array(values) => {
            output.push('[');
            for (index, value) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                write_canonical(value, output);
            }
            output.push(']');
        }
        Value::Object(values) => {
            output.push('{');
            for (index, (key, value)) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                write_string(key, output);
                output.push(':');
                write_canonical(value, output);
            }
            output.push('}');
        }
    }
}

fn write_pretty(value: &Value, depth: usize, output: &mut String) {
    match value {
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {
            write_canonical(value, output);
        }
        Value::Array(values) => {
            if values.is_empty() {
                output.push_str("[]");
                return;
            }
            output.push_str("[\n");
            for (index, value) in values.iter().enumerate() {
                indent(depth + 1, output);
                write_pretty(value, depth + 1, output);
                if index + 1 != values.len() {
                    output.push(',');
                }
                output.push('\n');
            }
            indent(depth, output);
            output.push(']');
        }
        Value::Object(values) => {
            if values.is_empty() {
                output.push_str("{}");
                return;
            }
            output.push_str("{\n");
            let len = values.len();
            for (index, (key, value)) in values.iter().enumerate() {
                indent(depth + 1, output);
                write_string(key, output);
                output.push_str(": ");
                write_pretty(value, depth + 1, output);
                if index + 1 != len {
                    output.push(',');
                }
                output.push('\n');
            }
            indent(depth, output);
            output.push('}');
        }
    }
}

fn indent(depth: usize, output: &mut String) {
    for _ in 0..depth {
        output.push_str("  ");
    }
}

fn write_string(value: &str, output: &mut String) {
    output.push('"');
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            '\u{0008}' => output.push_str("\\b"),
            '\u{000C}' => output.push_str("\\f"),
            character if character <= '\u{001F}' => {
                output.push_str(&format!("\\u{:04x}", character as u32));
            }
            character => output.push(character),
        }
    }
    output.push('"');
}

fn number_to_string(value: f64) -> String {
    if value.is_nan() || value.is_infinite() {
        return "null".to_string();
    }
    if value.fract() == 0.0 {
        format!("{:.0}", value)
    } else {
        let mut text = format!("{value}");
        if text.contains('E') {
            text = text.replace('E', "e");
        }
        text
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_roundtrip() {
        let input = r#"{"a":1,"b":[true,false,null],"c":"ok"}"#;
        let value = parse(input).unwrap();
        assert_eq!(to_canonical_string(&value), input);
    }

    #[test]
    fn test_parse_string_escape() {
        let input = r#""line\nnext""#;
        let value = parse(input).unwrap();
        assert_eq!(value.as_str(), Some("line\nnext"));
    }

    #[test]
    fn test_pretty_print_contains_newlines() {
        let value = parse(r#"{"z":2,"a":[1,2]}"#).unwrap();
        let pretty = to_pretty_string(&value);
        assert!(pretty.contains('\n'));
    }
}
