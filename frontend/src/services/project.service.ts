import axiosInstance from '@/lib/axios'
import {
    ProjectDatabaseRecordsResponse,
    ProjectDatabaseSchemaResponse,
    ProjectDeploymentResponse,
    ProjectDetails,
    ProjectSecretsResponse
} from '@/typings/project'

class ProjectService {
    async getSessionProject(sessionId: string): Promise<ProjectDetails> {
        const response = await axiosInstance.get<ProjectDetails>(
            `/project/${sessionId}`
        )
        return response.data
    }

    async getProjectSecrets(sessionId: string): Promise<ProjectSecretsResponse> {
        const response = await axiosInstance.get<ProjectSecretsResponse>(
            `/project/${sessionId}/secrets`
        )
        return response.data
    }

    async updateProjectSecrets(
        sessionId: string,
        secrets: Record<string, unknown>
    ): Promise<ProjectSecretsResponse> {
        const response = await axiosInstance.post<ProjectSecretsResponse>(
            `/project/${sessionId}/secrets`,
            { secrets }
        )
        return response.data
    }

    async getProjectDatabaseSchema(
        projectId: string
    ): Promise<ProjectDatabaseSchemaResponse> {
        const response = await axiosInstance.get<ProjectDatabaseSchemaResponse>(
            `/project/${projectId}/database/schema`
        )
        return response.data
    }

    async getProjectDatabaseRecords(
        projectId: string,
        params: { table: string; limit?: number; offset?: number }
    ): Promise<ProjectDatabaseRecordsResponse> {
        const response = await axiosInstance.get<ProjectDatabaseRecordsResponse>(
            `/project/${projectId}/database/records`,
            { params }
        )
        return response.data
    }

    async getProjectDeployment(
        projectId: string
    ): Promise<ProjectDeploymentResponse> {
        const response = await axiosInstance.get<ProjectDeploymentResponse>(
            `/project/${projectId}/deployment`
        )
        return response.data
    }
}

export const projectService = new ProjectService()
