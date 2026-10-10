//! KeyValues1 text format parser and serializer (AST-based) for config.vdf and .acf files.
//!
//! Provides lossless navigation and atomic updates without fragile regex or bracket counting.

use std::fmt::Write as FmtWrite;

#[derive(Debug, Clone, PartialEq)]
pub enum KvValue {
    String(String),
    Section(Vec<(String, KvValue)>),
}

impl KvValue {
    pub fn as_section(&self) -> Option<&[(String, KvValue)]> {
        match self {
            KvValue::Section(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_section_mut(&mut self) -> Option<&mut Vec<(String, KvValue)>> {
        match self {
            KvValue::Section(s) => Some(s),
            _ => None,
        }
    }

    pub fn get_str(&self, key: &str) -> Option<&str> {
        if let KvValue::Section(items) = self {
            for (k, v) in items {
                if k.eq_ignore_ascii_case(key) {
                    if let KvValue::String(s) = v {
                        return Some(s);
                    }
                }
            }
        }
        None
    }

    pub fn get_section(&self, key: &str) -> Option<&KvValue> {
        if let KvValue::Section(items) = self {
            for (k, v) in items {
                if k.eq_ignore_ascii_case(key) {
                    if matches!(v, KvValue::Section(_)) {
                        return Some(v);
                    }
                }
            }
        }
        None
    }

    pub fn get_section_mut(&mut self, key: &str) -> Option<&mut KvValue> {
        if let KvValue::Section(items) = self {
            for (k, v) in items {
                if k.eq_ignore_ascii_case(key) {
                    if matches!(v, KvValue::Section(_)) {
                        return Some(v);
                    }
                }
            }
        }
        None
    }

    pub fn get_or_create_section(&mut self, key: &str) -> &mut KvValue {
        if let KvValue::Section(items) = self {
            let pos = items.iter().position(|(k, v)| k.eq_ignore_ascii_case(key) && matches!(v, KvValue::Section(_)));
            if let Some(idx) = pos {
                return &mut items[idx].1;
            }
            items.push((key.to_string(), KvValue::Section(Vec::new())));
            let last_idx = items.len() - 1;
            return &mut items[last_idx].1;
        }
        panic!("called get_or_create_section on a non-section KvValue");
    }

    pub fn set_str(&mut self, key: &str, value: &str) {
        if let KvValue::Section(items) = self {
            if let Some((_, v)) = items.iter_mut().find(|(k, _)| k.eq_ignore_ascii_case(key)) {
                *v = KvValue::String(value.to_string());
            } else {
                items.push((key.to_string(), KvValue::String(value.to_string())));
            }
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum KvError {
    #[error("unexpected end of file")]
    UnexpectedEof,
    #[error("syntax error: {0}")]
    SyntaxError(String),
}

pub struct KeyValues {
    pub root: Vec<(String, KvValue)>,
}

impl KeyValues {
    pub fn parse(input: &str) -> Result<Self, KvError> {
        let tokens = tokenize(input)?;
        let mut idx = 0;
        let mut root = Vec::new();

        while idx < tokens.len() {
            let key = match &tokens[idx] {
                Token::Str(s) => s.clone(),
                Token::OpenBrace | Token::CloseBrace => {
                    return Err(KvError::SyntaxError("unexpected brace at root".into()));
                }
            };
            idx += 1;
            if idx >= tokens.len() {
                return Err(KvError::UnexpectedEof);
            }

            match &tokens[idx] {
                Token::OpenBrace => {
                    idx += 1;
                    let (sec, next_idx) = parse_section(&tokens, idx)?;
                    root.push((key, KvValue::Section(sec)));
                    idx = next_idx;
                }
                Token::Str(val) => {
                    root.push((key, KvValue::String(val.clone())));
                    idx += 1;
                }
                Token::CloseBrace => {
                    return Err(KvError::SyntaxError("unexpected closing brace".into()));
                }
            }
        }

        Ok(KeyValues { root })
    }

    pub fn serialize(&self) -> String {
        let mut out = String::new();
        for (k, v) in &self.root {
            serialize_node(k, v, 0, &mut out);
        }
        out
    }
}

#[derive(Debug, PartialEq)]
enum Token {
    Str(String),
    OpenBrace,
    CloseBrace,
}

fn tokenize(input: &str) -> Result<Vec<Token>, KvError> {
    let mut tokens = Vec::new();
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;
    let n = chars.len();

    while i < n {
        let c = chars[i];
        if c.is_whitespace() {
            i += 1;
            continue;
        }

        // Single-line comment //
        if c == '/' && i + 1 < n && chars[i + 1] == '/' {
            while i < n && chars[i] != '\n' && chars[i] != '\r' {
                i += 1;
            }
            continue;
        }

        if c == '{' {
            tokens.push(Token::OpenBrace);
            i += 1;
            continue;
        }

        if c == '}' {
            tokens.push(Token::CloseBrace);
            i += 1;
            continue;
        }

        if c == '"' {
            // Quoted string
            i += 1;
            let mut s = String::new();
            let mut escaped = false;
            while i < n {
                let ch = chars[i];
                if escaped {
                    s.push(ch);
                    escaped = false;
                } else if ch == '\\' {
                    escaped = true;
                } else if ch == '"' {
                    i += 1;
                    break;
                } else {
                    s.push(ch);
                }
                i += 1;
            }
            tokens.push(Token::Str(s));
            continue;
        }

        // Bare identifier
        let mut s = String::new();
        while i < n && !chars[i].is_whitespace() && chars[i] != '{' && chars[i] != '}' && chars[i] != '"' {
            s.push(chars[i]);
            i += 1;
        }
        tokens.push(Token::Str(s));
    }

    Ok(tokens)
}

fn parse_section(tokens: &[Token], mut idx: usize) -> Result<(Vec<(String, KvValue)>, usize), KvError> {
    let mut items = Vec::new();

    while idx < tokens.len() {
        match &tokens[idx] {
            Token::CloseBrace => {
                return Ok((items, idx + 1));
            }
            Token::Str(key) => {
                let k = key.clone();
                idx += 1;
                if idx >= tokens.len() {
                    return Err(KvError::UnexpectedEof);
                }
                match &tokens[idx] {
                    Token::OpenBrace => {
                        idx += 1;
                        let (sec, next_idx) = parse_section(tokens, idx)?;
                        items.push((k, KvValue::Section(sec)));
                        idx = next_idx;
                    }
                    Token::Str(val) => {
                        items.push((k, KvValue::String(val.clone())));
                        idx += 1;
                    }
                    Token::CloseBrace => {
                        return Err(KvError::SyntaxError("unexpected closing brace as value".into()));
                    }
                }
            }
            Token::OpenBrace => {
                return Err(KvError::SyntaxError("unexpected opening brace as key".into()));
            }
        }
    }

    Err(KvError::UnexpectedEof)
}

fn serialize_node(key: &str, val: &KvValue, indent: usize, out: &mut String) {
    let ind = "\t".repeat(indent);
    match val {
        KvValue::String(s) => {
            let _ = writeln!(out, "{}\"{}\"\t\t\"{}\"", ind, key, s);
        }
        KvValue::Section(children) => {
            let _ = writeln!(out, "{}\"{}\"\n{}{{\n", ind, key, ind);
            for (k, v) in children {
                serialize_node(k, v, indent + 1, out);
            }
            let _ = writeln!(out, "{}}}\n", ind);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_and_serialize_acf() {
        let input = r#"
"AppState"
{
	"appid"		"400"
	"Universe"		"1"
	"name"		"Portal"
	"StateFlags"		"4"
	"installdir"		"Portal"
	"InstalledDepots"
	{
		"401"
		{
			"manifest"		"123456789"
		}
	}
}
"#;
        let kv = KeyValues::parse(input).expect("parse acf failed");
        assert_eq!(kv.root.len(), 1);
        let root = &kv.root[0];
        assert_eq!(root.0, "AppState");
        assert_eq!(root.1.get_str("name"), Some("Portal"));
        assert_eq!(root.1.get_str("appid"), Some("400"));
        let depots = root.1.get_section("InstalledDepots").expect("missing depots");
        assert_eq!(depots.get_section("401").unwrap().get_str("manifest"), Some("123456789"));
    }
}
