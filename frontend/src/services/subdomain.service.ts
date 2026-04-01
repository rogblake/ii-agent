import axiosInstance from '@/lib/axios'

export interface CheckAvailabilityRequest {
    subdomain: string
}

export interface CheckAvailabilityResponse {
    subdomain: string
    available: boolean
    full_domain: string | null
    error: string | null
    suggestions: string[] | null
}

export interface SubdomainResponse {
    success: boolean
    subdomain: string | null
    full_domain: string | null
    status: string | null
    cloud_run_url: string | null
    error: string | null
}

export interface BaseDomainInfoResponse {
    base_domain: string
    example: string
    proxied: boolean
}

export interface ClaimSubdomainRequest {
    project_id: string
    subdomain: string
}

export interface ClaimSubdomainResponse {
    success: boolean
    subdomain: string | null
    full_domain: string | null
    production_url: string | null
    error: string | null
}

class SubdomainService {
    async checkAvailability(
        subdomain: string
    ): Promise<CheckAvailabilityResponse> {
        const response = await axiosInstance.post<CheckAvailabilityResponse>(
            '/v1/project/subdomains/check-availability',
            { subdomain }
        )
        return response.data
    }

    async getSubdomain(subdomain: string): Promise<SubdomainResponse> {
        const response = await axiosInstance.get<SubdomainResponse>(
            `/v1/project/subdomains/${subdomain}`
        )
        return response.data
    }

    async getBaseDomainInfo(): Promise<BaseDomainInfoResponse> {
        const response = await axiosInstance.get<BaseDomainInfoResponse>(
            '/v1/project/subdomains/base-domain/info'
        )
        return response.data
    }

    async getReservedSubdomains(): Promise<{ reserved: string[] }> {
        const response = await axiosInstance.get<{ reserved: string[] }>(
            '/v1/project/subdomains/reserved'
        )
        return response.data
    }

    async claimSubdomain(
        projectId: string,
        subdomain: string
    ): Promise<ClaimSubdomainResponse> {
        const response = await axiosInstance.post<ClaimSubdomainResponse>(
            '/v1/project/subdomains/claim',
            { project_id: projectId, subdomain }
        )
        return response.data
    }
}

export const subdomainService = new SubdomainService()
