import { api, setToken, toApiError } from "@/lib/api";
import type {
  LoginInput,
  RegisterInput,
  TokenResponse,
  User,
} from "@/types";

export async function login(input: LoginInput): Promise<TokenResponse> {
  try {
    const { data } = await api.post<TokenResponse>("/auth/login", input);
    setToken(data.access_token);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function register(input: RegisterInput): Promise<User> {
  try {
    const { data } = await api.post<User>("/auth/register", input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function registerAndLogin(input: RegisterInput): Promise<TokenResponse> {
  await register(input);
  return login({ email: input.email, password: input.password });
}

export async function fetchMe(): Promise<User> {
  try {
    const { data } = await api.get<User>("/auth/me");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function updateProfile(input: { name: string }): Promise<User> {
  try {
    const { data } = await api.patch<User>("/auth/me", input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
