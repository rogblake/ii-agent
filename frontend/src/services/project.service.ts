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
            `/v1/project/${sessionId}`
        )
        return response.data
    }

    async getProjectSecrets(sessionId: string): Promise<ProjectSecretsResponse> {
        const response = await axiosInstance.get<ProjectSecretsResponse>(
            `/v1/project/${sessionId}/secrets`
        )
        return response.data
    }

    async addProjectSecrets(
        sessionId: string,
        secrets: Record<string, unknown>
    ): Promise<ProjectSecretsResponse> {
        const response = await axiosInstance.post<ProjectSecretsResponse>(
            `/v1/project/${sessionId}/secrets`,
            { secrets }
        )
        return response.data
    }

    async replaceProjectSecrets(
        sessionId: string,
        secrets: Record<string, unknown>
    ): Promise<ProjectSecretsResponse> {
        const response = await axiosInstance.put<ProjectSecretsResponse>(
            `/v1/project/${sessionId}/secrets`,
            { secrets }
        )
        return response.data
    }

    async deleteProjectSecrets(
        sessionId: string,
        secretKeys: string[]
    ): Promise<ProjectSecretsResponse> {
        const response = await axiosInstance.delete<ProjectSecretsResponse>(
            `/v1/project/${sessionId}/secrets`,
            {
                data: {
                    secret_keys: secretKeys
                }
            }
        )
        return response.data
    }

    async getProjectDatabaseSchema(
        projectId: string
    ): Promise<ProjectDatabaseSchemaResponse> {
        const response = await axiosInstance.get<ProjectDatabaseSchemaResponse>(
            `/v1/project/${projectId}/database/schema`
        )
        return response.data
    }

    async getProjectDatabaseRecords(
        projectId: string,
        params: { table: string; limit?: number; offset?: number }
    ): Promise<ProjectDatabaseRecordsResponse> {
        const response = await axiosInstance.get<ProjectDatabaseRecordsResponse>(
            `/v1/project/${projectId}/database/records`,
            { params }
        )
        return response.data
    }

    async getProjectDeployment(
        projectId: string
    ): Promise<ProjectDeploymentResponse> {
        const response = await axiosInstance.get<ProjectDeploymentResponse>(
            `/v1/project/${projectId}/deployment`
        )
        return response.data
    }
}

export const projectService = new ProjectService()
