package types

import "time"

const (
	// PluginTranslationSourceMarketplace identifies a translation attached to a marketplace item.
	PluginTranslationSourceMarketplace = "marketplace"
	// PluginTranslationSourceOrganization identifies a translation attached to an organization plugin.
	PluginTranslationSourceOrganization = "organization"
	// PluginTranslationSourceSystem identifies a fixed translation attached to a system plugin.
	PluginTranslationSourceSystem = "system"
)

// PluginTranslation stores display translations for one immutable Skill source revision.
// Organization and marketplace rows are scoped to OrgID; system rows use OrgID 0
// and point to a system plugin by SourceID.
type PluginTranslation struct {
	ID uint `gorm:"column:id;primaryKey"`

	OrgID            uint   `gorm:"column:org_id;type:bigint;not null;uniqueIndex:ux_plugin_translation_scope,priority:1"`
	SourceType       string `gorm:"column:source_type;type:varchar(32);not null;uniqueIndex:ux_plugin_translation_scope,priority:2;index:idx_plugin_translation_source_revision,priority:1;check:chk_plugin_translation_source_type,source_type IN ('marketplace','organization','system')"`
	SourceID         uint   `gorm:"column:source_id;type:bigint;not null;uniqueIndex:ux_plugin_translation_scope,priority:3;index:idx_plugin_translation_source_revision,priority:2"`
	PluginRevisionID uint   `gorm:"column:plugin_revision_id;type:bigint;not null;uniqueIndex:ux_plugin_translation_scope,priority:4;index:idx_plugin_translation_source_revision,priority:3"`
	SourceRevision   int    `gorm:"column:source_revision;type:integer;not null"`
	Locale           string `gorm:"column:locale;type:varchar(16);not null;default:'zh-CN';uniqueIndex:ux_plugin_translation_scope,priority:5"`

	MetadataSourceHash    string `gorm:"column:metadata_source_hash;type:varchar(64);not null;default:''"`
	TranslatedName        string `gorm:"column:translated_name;type:varchar(255);not null;default:''"`
	TranslatedDescription string `gorm:"column:translated_description;type:text;not null;default:''"`
	SkillMDSourceHash     string `gorm:"column:skill_md_source_hash;type:varchar(64);not null;default:''"`
	TranslatedSkillMD     string `gorm:"column:translated_skill_md;type:text;not null;default:''"`

	CreatedAt time.Time `gorm:"column:created_at;not null"`
	UpdatedAt time.Time `gorm:"column:updated_at;not null"`
}

// TableName returns the Skill presentation translation cache table.
func (PluginTranslation) TableName() string {
	return TableNamePluginTranslation
}
