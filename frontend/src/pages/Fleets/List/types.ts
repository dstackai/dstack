export type TPoolWithProject = IPoolListItem & { project_name: string };

export type TFleetInstance = Partial<IInstance> & { fleetName: IFleet['name'] };
