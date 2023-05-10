package models

import "strings"

type Escaper struct {
	chars      map[string]string
	escapeChar string
	encoder    *strings.Replacer
}

func NewEscaper(chars map[string]string, escapeChar string) *Escaper {
	e := &Escaper{
		chars:      chars,
		escapeChar: escapeChar,
	}
	var tokens []string
	tokens = append(tokens, escapeChar, escapeChar+escapeChar)
	for from, to := range chars {
		tokens = append(tokens, from, escapeChar+to)
	}
	e.encoder = strings.NewReplacer(tokens...)
	return e
}

func (e *Escaper) Escape(v string) string {
	return e.encoder.Replace(v)
}

//func (e *Escaper) Unescape(v string) (string, error) {}

var headEscaper = NewEscaper(map[string]string{"/": "."}, "~")

func EscapeHead(v string) string {
	return headEscaper.Escape(v)
}
