package config

import (
	"fmt"
	"strings"

	ygconfig "github.com/ygpkg/yg-go/config"
	"go.uber.org/zap/zapcore"
	"gopkg.in/natefinch/lumberjack.v2"
)

// LogConfig configures application logging.
type LogConfig struct {
	Level string `yaml:"level,omitempty" json:"level,omitempty"`
}

// LogsConfig configures named logger outputs such as default and gorm.
type LogsConfig map[string][]LogWriterConfig

// LogWriterConfig configures one logger output.
type LogWriterConfig struct {
	Writer     string            `yaml:"writer" json:"writer"`
	Encoder    string            `yaml:"encoder,omitempty" json:"encoder,omitempty"`
	Level      string            `yaml:"level,omitempty" json:"level,omitempty"`
	Key        string            `yaml:"key,omitempty" json:"key,omitempty"`
	Filename   string            `yaml:"filename,omitempty" json:"filename,omitempty"`
	MaxSize    int               `yaml:"maxsize,omitempty" json:"maxsize,omitempty"`
	MaxAge     int               `yaml:"maxage,omitempty" json:"maxage,omitempty"`
	MaxBackups int               `yaml:"maxbackups,omitempty" json:"maxbackups,omitempty"`
	LocalTime  bool              `yaml:"localtime,omitempty" json:"localtime,omitempty"`
	Compress   bool              `yaml:"compress,omitempty" json:"compress,omitempty"`
	TencentCLS *TencentCLSConfig `yaml:"tencent_cls,omitempty" json:"tencent_cls,omitempty"`
}

// TencentCLSConfig configures a Tencent Cloud CLS topic.
type TencentCLSConfig struct {
	TopicID   string `yaml:"topic_id" json:"topic_id"`
	SecretID  string `yaml:"secret_id" json:"secret_id"`
	SecretKey string `yaml:"secret_key" json:"secret_key"`
	Region    string `yaml:"region" json:"region"`
	Endpoint  string `yaml:"endpoint" json:"endpoint"`
}

// ToYGConfig converts application logging configuration into yg-go logging configuration.
func (c LogsConfig) ToYGConfig() (ygconfig.LogsConfig, error) {
	result := make(ygconfig.LogsConfig, len(c))
	for name, outputs := range c {
		converted := make([]ygconfig.LogConfig, 0, len(outputs))
		for index, output := range outputs {
			writer := strings.ToLower(strings.TrimSpace(output.Writer))
			switch writer {
			case "", "console", "stdout", "file", "workwx", "cls", "tencent", "tencentcls":
			default:
				return nil, fmt.Errorf("logger %q output %d has unsupported writer %q", name, index, output.Writer)
			}
			if writer == "cls" || writer == "tencent" || writer == "tencentcls" {
				if output.TencentCLS == nil {
					return nil, fmt.Errorf("logger %q output %d requires tencent_cls configuration", name, index)
				}
				if strings.TrimSpace(output.TencentCLS.TopicID) == "" ||
					strings.TrimSpace(output.TencentCLS.SecretID) == "" ||
					strings.TrimSpace(output.TencentCLS.SecretKey) == "" ||
					strings.TrimSpace(output.TencentCLS.Endpoint) == "" {
					return nil, fmt.Errorf("logger %q output %d has incomplete tencent_cls configuration", name, index)
				}
			}

			level := zapcore.InfoLevel
			if value := strings.TrimSpace(output.Level); value != "" {
				if err := level.UnmarshalText([]byte(value)); err != nil {
					return nil, fmt.Errorf("logger %q output %d has invalid level %q: %w", name, index, output.Level, err)
				}
			}

			item := ygconfig.LogConfig{
				Writer:  writer,
				Encoder: output.Encoder,
				Level:   level,
				Key:     output.Key,
			}
			if writer == "file" {
				item.Logger = &lumberjack.Logger{
					Filename:   output.Filename,
					MaxSize:    output.MaxSize,
					MaxAge:     output.MaxAge,
					MaxBackups: output.MaxBackups,
					LocalTime:  output.LocalTime,
					Compress:   output.Compress,
				}
			}
			if output.TencentCLS != nil {
				item.TencentCLS = &ygconfig.TencentCLSConfig{
					TopicID: output.TencentCLS.TopicID,
					TencentConfig: ygconfig.TencentConfig{
						SecretID:  output.TencentCLS.SecretID,
						SecretKey: output.TencentCLS.SecretKey,
						Region:    output.TencentCLS.Region,
						Endpoint:  output.TencentCLS.Endpoint,
					},
				}
			}
			converted = append(converted, item)
		}
		result[name] = converted
	}
	return result, nil
}
