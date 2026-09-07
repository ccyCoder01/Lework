package types

import (
	"gorm.io/gorm"
)

// DigitalAssistantVisibility 表示 AI 队友在组织内的可见范围。
type DigitalAssistantVisibility string

const (
	// DigitalAssistantVisibilityPublic 表示组织成员可查看和使用。
	DigitalAssistantVisibilityPublic DigitalAssistantVisibility = "public"
	// DigitalAssistantVisibilityPrivate 表示仅直接授权成员可查看和使用。
	DigitalAssistantVisibilityPrivate DigitalAssistantVisibility = "private"
)

// ValidDigitalAssistantVisibility 判断 visibility 是否为合法值。
func ValidDigitalAssistantVisibility(v DigitalAssistantVisibility) bool {
	return v == DigitalAssistantVisibilityPublic || v == DigitalAssistantVisibilityPrivate
}

// DefaultDigitalAssistantPublicIDPrefix identifies organization-level system assistants.
const DefaultDigitalAssistantPublicIDPrefix = "assistant_default_"

// DigitalAssistant 数字助手结构体定义了AI数字助手的基本信息与配置
type DigitalAssistant struct {
	gorm.Model
	// digital_assistant - 公开标识符，在组织内唯一标识数字助手，VARCHAR(255)，NOT NULL
	PublicID string `gorm:"column:public_id;type:varchar(255);not null;uniqueIndex"`

	// digital_assistant - 所属组织ID，INTEGER，NOT NULL
	OrgID uint `gorm:"column:org_id;type:integer;not null;index"`
	// digital_assistant - 组织内可见范围，VARCHAR(16)，NOT NULL
	Visibility DigitalAssistantVisibility `gorm:"column:visibility;type:varchar(16);not null;default:'private';check:chk_digital_assistant_visibility,visibility IN ('public','private')"`
	// digital_assistant - 拥有者ID，INTEGER，NOT NULL
	OwnerID uint `gorm:"column:owner_id;type:integer;not null;index"`

	// digital_assistant - 数字助手名称，VARCHAR(255)，NOT NULL
	Name string `gorm:"column:name;type:varchar(255);not null"`
	// digital_assistant - 对外展示的角色名称，VARCHAR(255)，允许为空以兼容历史数据
	RoleName string `gorm:"column:role_name;type:varchar(255)"`

	// digital_assistant - 描述信息，TEXT，允许为空
	Description string `gorm:"column:description;type:text"`
	// digital_assistant - 头像URL地址，VARCHAR(500)，允许为空
	Avatar string `gorm:"column:avatar;type:varchar(500)"`

	// digital_assistant - 状态，表示数字助手当前运行状态，VARCHAR(50)，NOT NULL
	Status string `gorm:"column:status;type:varchar(50);not null"`
	// digital_assistant - 版本号，跟踪配置变动版本，INTEGER，默认值0
	Version int `gorm:"column:version;type:integer;default:0"`
	// digital_assistant - 系统提示词，定义数字助手的角色和行为，TEXT，允许为空
	SystemPrompt string `gorm:"column:system_prompt;type:text"`
	// digital_assistant - 擅长领域列表，JSONB，允许为空
	Expertise SkillStringList `gorm:"column:expertise;type:jsonb"`
	// digital_assistant - 来源模板ID，INTEGER，允许为空
	TemplateID *uint `gorm:"column:template_id;type:integer;index"`
	// digital_assistant - 创建来源，VARCHAR(32)，NOT NULL
	Source string `gorm:"column:source;type:varchar(32);not null;default:custom;index"`
}

// TableName 指定DigitalAssistant结构体对应的数据库表名
func (DigitalAssistant) TableName() string {
	return TableNameDigitalAssistant
}
