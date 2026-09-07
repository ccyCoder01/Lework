package service

import (
	"fmt"
	"regexp"
	"strings"
)

var connectorBindingTemplatePattern = regexp.MustCompile(`\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}`)

// RenderConnectorBinding resolves credential placeholders without reusing deployment environment syntax.
func RenderConnectorBinding(expression string, values map[string]string) (string, bool, error) {
	references, direct, err := connectorBindingReferences(expression)
	if err != nil {
		return "", false, err
	}
	if direct {
		value := values[references[0]]
		return value, value != "", nil
	}
	for _, reference := range references {
		if values[reference] == "" {
			return "", false, nil
		}
	}
	resolved := connectorBindingTemplatePattern.ReplaceAllStringFunc(expression, func(match string) string {
		parts := connectorBindingTemplatePattern.FindStringSubmatch(match)
		return values[parts[1]]
	})
	return resolved, true, nil
}

func validateConnectorBinding(expression string, knownValues map[string]struct{}) error {
	references, _, err := connectorBindingReferences(expression)
	if err != nil {
		return err
	}
	if knownValues == nil {
		return nil
	}
	for _, reference := range references {
		if _, exists := knownValues[reference]; !exists {
			return fmt.Errorf("binding references unknown credential %q", reference)
		}
	}
	return nil
}

func connectorBindingReferences(expression string) ([]string, bool, error) {
	if expression == "" || strings.ContainsRune(expression, '\x00') {
		return nil, false, fmt.Errorf("binding expression is invalid")
	}
	if envNamePattern.MatchString(expression) {
		return []string{expression}, true, nil
	}
	matches := connectorBindingTemplatePattern.FindAllStringSubmatchIndex(expression, -1)
	if len(matches) == 0 {
		return nil, false, fmt.Errorf("binding expression must reference a credential")
	}
	references := make([]string, 0, len(matches))
	previousEnd := 0
	for _, match := range matches {
		if hasUnmatchedBindingDelimiter(expression[previousEnd:match[0]]) {
			return nil, false, fmt.Errorf("binding expression template is invalid")
		}
		references = append(references, expression[match[2]:match[3]])
		previousEnd = match[1]
	}
	if hasUnmatchedBindingDelimiter(expression[previousEnd:]) {
		return nil, false, fmt.Errorf("binding expression template is invalid")
	}
	return references, false, nil
}

func hasUnmatchedBindingDelimiter(value string) bool {
	return strings.Contains(value, "{{") || strings.Contains(value, "}}")
}
