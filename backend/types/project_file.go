package types

import (
	"gorm.io/gorm"
)

// ProjectFileResourceType 项目文件关联的资源类型
type ProjectFileResourceType string

const (
	ProjectFileResourceTypeUserUpload ProjectFileResourceType = "user_upload" // 用户上传
	ProjectFileResourceTypeArtifact   ProjectFileResourceType = "artifact"    // 工作产物
	ProjectFileResourceTypePlan       ProjectFileResourceType = "plan"        // 计划文件
)

// ProjectFile 项目文件关联表，记录项目/任务/资源之间的映射关系
type ProjectFile struct {
	gorm.Model
	FilePublicID string                  `gorm:"column:file_public_id;type:varchar(255);not null;index"`
	OrgID        uint                    `gorm:"column:org_id;type:integer;not null;index;index:idx_project_file_path,priority:1;index:idx_project_file_version_lookup,priority:1"`
	ProjectID    uint                    `gorm:"column:project_id;type:bigint;not null;index;index:idx_project_file_path,priority:2;index:idx_project_file_version_lookup,priority:2"`
	TaskID       uint                    `gorm:"column:task_id;type:bigint;index"`
	ResourceID   uint                    `gorm:"column:resource_id;type:bigint;not null;default:0;index"`
	ResourceType ProjectFileResourceType `gorm:"column:resource_type;type:varchar(50);not null;index;index:idx_project_file_path,priority:3"`
	Uin          uint                    `gorm:"column:uin;type:bigint;index"`

	RelativePath        string `gorm:"column:relative_path;type:varchar(1000);not null;default:'';index:idx_project_file_path,priority:4"`
	InitialFilePublicID string `gorm:"column:initial_file_public_id;type:varchar(255);not null;default:'';index;index:idx_project_file_version_lookup,priority:3"`
	VersionNo           int    `gorm:"column:version_no;type:integer;not null;default:1;index:idx_project_file_version_lookup,priority:4"`
}

func (ProjectFile) TableName() string {
	return TableNameProjectFile
}
