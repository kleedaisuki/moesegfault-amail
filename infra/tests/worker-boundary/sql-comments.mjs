/** Remove SQLite line comments before passing a migration to Miniflare D1.exec(). */
export function stripSqlLineComments(sql) {
  let result = "";
  let quote = null;
  for (let i = 0; i < sql.length; i++) {
    const char = sql[i];
    if (quote !== null) {
      result += char;
      if (char === quote) {
        if (sql[i + 1] === quote) result += sql[++i];
        else quote = null;
      }
      continue;
    }
    if (char === "'" || char === '"' || char === "`" || char === "[") {
      quote = char === "[" ? "]" : char;
      result += char;
      continue;
    }
    if (char === "-" && sql[i + 1] === "-") {
      while (i < sql.length && sql[i] !== "\n") i++;
      if (i < sql.length) result += "\n";
      continue;
    }
    result += char;
  }
  // A comment-only prefix/suffix must not become an empty D1 statement.
  return result.trim();
}
